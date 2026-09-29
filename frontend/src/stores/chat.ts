import { defineStore } from 'pinia'
import { SSEChatClient } from '../api/sse'
import { useSettingsStore } from './settings'
import { parseApprovalData, type ApprovalData } from '../utils/approval'

/**
 * 单次工具调用状态记录
 */
export interface ToolCallItem {
  id: string
  name: string
  input: any
  output?: string
  status: 'running' | 'completed' | 'error'
}

/**
 * 用户上传的附件文档元信息
 */
export interface AttachedDocMeta {
  name: string
  size: number
  isPdf?: boolean
  pages?: number
}

/**
 * 长程任务规划步骤项
 */
export interface PlanStepItem {
  id: number
  title: string
  description?: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  result?: string
}

/**
 * 对话单条消息结构体定义
 */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  images?: string[]
  docs?: AttachedDocMeta[]
  thought?: string
  /** 思考规划用时（秒，保留 1 位小数） */
  thoughtDuration?: number
  tools?: ToolCallItem[]
  currentNode?: string
  isStreaming?: boolean
  error?: string
  timestamp: number
  /** 待确认的敏感高危操作数据（如有） */
  approvalData?: ApprovalData | null
  /** 用户审批状态：'pending' (待确认) | 'approved' (已批准) | 'rejected' (已拒绝) */
  approvalStatus?: 'pending' | 'approved' | 'rejected'
  /** 长程任务规划状态列表 (Plan-and-Solve) */
  plan?: PlanStepItem[]
  /** 动态路由命中的模型与层级 */
  routedModel?: {
    model: string
    tier?: string
    reason?: string
  }
}

/**
 * 会话元信息定义
 */
export interface SessionInfo {
  id: string
  title: string
  updatedAt: number
}

/**
 * 会话独立滚动位置与吸底状态记录
 */
export interface SessionScrollState {
  scrollTop: number
  isAtBottom: boolean
}

const sseClient = new SSEChatClient()

/**
 * 对话交互核心 Pinia Store：负责会话历史、流式消息接收与工具调用追踪
 */
export const useChatStore = defineStore('chat', {
  state: () => ({
    // 当前激活的会话 ID
    currentSessionId: localStorage.getItem('agent_active_session') || 'session_' + Date.now(),
    // 历史会话列表
    sessions: (JSON.parse(localStorage.getItem('agent_sessions_list') || '[]')) as SessionInfo[],
    // 当前会话的消息流列表
    messages: [] as ChatMessage[],
    // 智能体当前运行模式：'chat' | 'react' | 'multi_agent' | 'rag'
    activeMode: 'react',
    // 是否正在处于流式推理生成中
    isGenerating: false,
    // 各会话独立滚动位置与吸底状态缓存 (保持每个会话滚动位置互不干扰)
    sessionScrolls: (JSON.parse(sessionStorage.getItem('agent_session_scrolls') || '{}')) as Record<string, SessionScrollState>,
  }),

  actions: {
    /** 初始化会话状态 */
    initSession() {
      // 1. 清理历史上遗留的无消息空会话
      this.sessions = this.sessions.filter(s => {
        const cached = localStorage.getItem(`agent_msgs_${s.id}`)
        if (!cached) return false
        try {
          const msgs = JSON.parse(cached)
          return Array.isArray(msgs) && msgs.length > 0
        } catch {
          return false
        }
      })
      localStorage.setItem('agent_sessions_list', JSON.stringify(this.sessions))

      // 2. 检查上次活跃的会话是否有效
      const activeId = localStorage.getItem('agent_active_session')
      const found = this.sessions.find(s => s.id === activeId)

      if (found) {
        this.loadSessionMessages(found.id)
      } else if (this.sessions.length > 0) {
        this.loadSessionMessages(this.sessions[0].id)
      } else {
        // 如果当前没有任何历史会话，直接进入全新待发对话状态
        this.createNewSession()
      }
    },

    /** 创建全新对话（进入全新对话，但不加入历史列表，直到用户发送问题后才保存） */
    createNewSession() {
      // 如果当前已经是未发送任何消息的全新对话，直接停留在当前状态
      const isCurrentSaved = this.sessions.some(s => s.id === this.currentSessionId)
      if (!isCurrentSaved && this.messages.length === 0) {
        return
      }

      const settings = useSettingsStore()
      this.currentSessionId = 'session_' + Date.now()
      this.messages = []
      this.activeMode = settings.defaultMode || 'react'
      // 仅记录当前临时 session ID，不将其存入 this.sessions 历史列表中
      localStorage.setItem('agent_active_session', this.currentSessionId)
    },

    /** 加载指定会话的消息历史 */
    loadSessionMessages(sessionId: string) {
      if (this.currentSessionId === sessionId && this.messages.length > 0) {
        return
      }
      this.currentSessionId = sessionId
      localStorage.setItem('agent_active_session', sessionId)
      const cached = localStorage.getItem(`agent_msgs_${sessionId}`)
      if (cached) {
        try {
          const parsed: ChatMessage[] = JSON.parse(cached)
          // 兜底修复历史会话中残留的 running 或 streaming 状态，防止重新加载后持续转圈
          for (const m of parsed) {
            m.isStreaming = false
            if (m.tools) {
              for (const t of m.tools) {
                if (t.status === 'running') {
                  t.status = m.error ? 'error' : 'completed'
                  if (!t.output) {
                    t.output = m.error ? `执行中断: ${m.error}` : '已完成（历史记录）'
                  }
                }
              }
            }
          }
          this.messages = parsed
        } catch {
          this.messages = []
        }
      } else {
        this.messages = []
      }
    },

    /** 保存指定会话的滚动状态与是否吸底 */
    saveSessionScroll(sessionId: string, scrollTop: number, isAtBottom: boolean) {
      if (!sessionId) return
      this.sessionScrolls[sessionId] = { scrollTop, isAtBottom }
      try {
        sessionStorage.setItem('agent_session_scrolls', JSON.stringify(this.sessionScrolls))
      } catch {}
    },

    /** 获取指定会话保存的滚动状态 */
    getSessionScroll(sessionId: string): SessionScrollState | undefined {
      return this.sessionScrolls[sessionId]
    },

    /** 自定义重命名指定会话标题 */
    renameSession(sessionId: string, newTitle: string) {
      const trimmed = newTitle.trim()
      if (!trimmed) return
      const target = this.sessions.find(s => s.id === sessionId)
      if (target) {
        target.title = trimmed
        target.updatedAt = Date.now()
        this.saveSessions()
      }
    },

    /** 当 LocalStorage 配额紧张时自动修剪历史大图缓存，杜绝 QuotaExceededError 崩溃 */
    pruneOldStorageQuota() {
      try {
        for (let i = this.sessions.length - 1; i >= 0; i--) {
          const s = this.sessions[i]
          if (s.id === this.currentSessionId) continue
          const raw = localStorage.getItem(`agent_msgs_${s.id}`)
          if (raw && raw.includes('data:image')) {
            const msgs = JSON.parse(raw)
            for (const m of msgs) {
              if (m.images) m.images = []
            }
            localStorage.setItem(`agent_msgs_${s.id}`, JSON.stringify(msgs))
            console.log(`[Storage] 已优化历史会话 ${s.id} 的大图缓存以释放配额`)
            return
          }
        }
      } catch (e) {
        console.warn('[Storage] 自动修剪配额仍不足', e)
      }
    },

    /** 持久化会话列表及当前消息流到本地存储 (带安全配额防爆容错) */
    saveSessions() {
      try {
        localStorage.setItem('agent_sessions_list', JSON.stringify(this.sessions))
        localStorage.setItem('agent_active_session', this.currentSessionId)
        if (this.sessions.some(s => s.id === this.currentSessionId) && this.messages.length > 0) {
          localStorage.setItem(`agent_msgs_${this.currentSessionId}`, JSON.stringify(this.messages))
        } else {
          localStorage.removeItem(`agent_msgs_${this.currentSessionId}`)
        }
      } catch (err) {
        console.warn('LocalStorage 写入异常，执行配额防爆容错处理...', err)
        this.pruneOldStorageQuota()
        try {
          if (this.sessions.some(s => s.id === this.currentSessionId) && this.messages.length > 0) {
            localStorage.setItem(`agent_msgs_${this.currentSessionId}`, JSON.stringify(this.messages))
          }
        } catch {}
      }
    },

    /** 删除指定会话 */
    deleteSession(sessionId: string) {
      this.sessions = this.sessions.filter(s => s.id !== sessionId)
      localStorage.removeItem(`agent_msgs_${sessionId}`)
      delete this.sessionScrolls[sessionId]
      try {
        sessionStorage.setItem('agent_session_scrolls', JSON.stringify(this.sessionScrolls))
        // 异步通知后端清理对应 session 的 Checkpoint 内存状态
        fetch(`http://127.0.0.1:8000/api/chat/sessions/${sessionId}`, { method: 'DELETE' }).catch(() => {})
      } catch {}
      if (this.currentSessionId === sessionId) {
        if (this.sessions.length > 0) {
          this.loadSessionMessages(this.sessions[0].id)
        } else {
          this.createNewSession()
        }
      }
      this.saveSessions()
    },

    /** 重新生成指定助手回复 */
    async regenerateMessage(assistantMsgId: string) {
      if (this.isGenerating) return
      const idx = this.messages.findIndex(m => m.id === assistantMsgId)
      if (idx <= 0) return

      let userMsgIndex = -1
      for (let i = idx - 1; i >= 0; i--) {
        if (this.messages[i].role === 'user') {
          userMsgIndex = i
          break
        }
      }
      if (userMsgIndex === -1) return

      const userMsg = this.messages[userMsgIndex]
      const promptText = userMsg.content || ''
      const images = userMsg.images
      const docs = userMsg.docs

      // 移除原有的助手消息与对应的用户消息（sendMessage 会重新创建并压入）
      this.messages.splice(idx, 1)
      this.messages.splice(userMsgIndex, 1)
      this.saveSessions()

      await this.sendMessage(promptText, images, docs)
    },

    /** 清空当前会话的消息记录（转回全新未保存对话） */
    clearCurrentSessionMessages() {
      this.messages = []
      localStorage.removeItem(`agent_msgs_${this.currentSessionId}`)
      delete this.sessionScrolls[this.currentSessionId]
      try {
        sessionStorage.setItem('agent_session_scrolls', JSON.stringify(this.sessionScrolls))
      } catch {}
      this.sessions = this.sessions.filter(s => s.id !== this.currentSessionId)
      this.createNewSession()
      this.saveSessions()
    },

    /** 清空所有历史会话 */
    clearAllSessions() {
      for (const s of this.sessions) {
        localStorage.removeItem(`agent_msgs_${s.id}`)
      }
      this.sessions = []
      this.messages = []
      this.sessionScrolls = {}
      try {
        sessionStorage.removeItem('agent_session_scrolls')
      } catch {}
      localStorage.removeItem('agent_sessions_list')
      localStorage.removeItem('agent_active_session')
      this.createNewSession()
    },

    /** 发送消息并开启 SSE 流式接收（支持文本、多模态图片与文档附件） */
    async sendMessage(
      text: string,
      images?: string[],
      docsMeta?: AttachedDocMeta[],
      fullPrompt?: string
    ) {
      const hasImages = Array.isArray(images) && images.length > 0
      const hasDocs = Array.isArray(docsMeta) && docsMeta.length > 0
      const actualPrompt = fullPrompt || text
      if ((!actualPrompt.trim() && !hasImages && !hasDocs) || this.isGenerating) return

      const settings = useSettingsStore()
      const trimmedText = text.trim()
      let displayTitle = ''
      if (trimmedText) {
        displayTitle = trimmedText.slice(0, 24) + (trimmedText.length > 24 ? '...' : '')
      } else if (hasDocs) {
        displayTitle = (docsMeta![0].isPdf ? '[PDF] ' : '[文档] ') + docsMeta![0].name
      } else {
        displayTitle = '[图片] 图像多模态分析'
      }

      // 1. 检查当前会话是否在历史列表中；若不在（新建对话后首次提问），此时才正式保存到历史列表中！
      let sess = this.sessions.find(s => s.id === this.currentSessionId)
      if (!sess) {
        sess = {
          id: this.currentSessionId,
          title: displayTitle,
          updatedAt: Date.now(),
        }
        this.sessions.unshift(sess)
      } else {
        if (sess.title === '新对话') {
          sess.title = displayTitle
        }
        sess.updatedAt = Date.now()
        // 将活跃会话移至最顶端
        const idx = this.sessions.findIndex(s => s.id === this.currentSessionId)
        if (idx > 0) {
          const [moved] = this.sessions.splice(idx, 1)
          this.sessions.unshift(moved)
        }
      }

      // 2. 追加用户提问消息（包含多模态图片与文档元信息）
      const userMsg: ChatMessage = {
        id: 'msg_' + Date.now(),
        role: 'user',
        content: trimmedText,
        images: hasImages ? [...images!] : undefined,
        docs: hasDocs ? [...docsMeta!] : undefined,
        timestamp: Date.now(),
      }
      this.messages.push(userMsg)

      // 3. 创建助手占位消息，准备流式渲染
      const assistantMsgId = 'msg_asst_' + Date.now()
      const assistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        thought: '',
        tools: [],
        isStreaming: true,
        timestamp: Date.now(),
      }
      this.messages.push(assistantMsg)
      this.isGenerating = true
      this.saveSessions()

      const targetMsg = this.messages.find(m => m.id === assistantMsgId)!
      let thoughtStartTime: number | null = null
      let thoughtEndTime: number | null = null

      // 4. 建立 SSE 流式传输通道（向智能体传输包含文档完整内容的 actualPrompt）
      await sseClient.streamChat(
        {
          message: actualPrompt,
          session_id: this.currentSessionId,
          mode: this.activeMode,
          model: settings.model,
          base_url: settings.baseUrl,
          api_key: settings.apiKey,
          temperature: settings.temperature,
          approval_mode: settings.approvalMode,
          images: hasImages ? images : undefined,
        },
        {
          // 接收大模型常规文本 Token
          onToken: (token) => {
            if (thoughtStartTime && !thoughtEndTime) {
              thoughtEndTime = Date.now()
              targetMsg.thoughtDuration = Math.max(0.1, Number(((thoughtEndTime - thoughtStartTime) / 1000).toFixed(1)))
            }
            targetMsg.content += token
          },
          // 接收思考链 Token (DeepSeek-R1 等)
          onThought: (thought) => {
            if (!thoughtStartTime) {
              thoughtStartTime = Date.now()
            }
            targetMsg.thought = (targetMsg.thought || '') + thought
          },
          // 收到工具调用开始通知
          onToolStart: (toolName, inputArgs) => {
            if (!targetMsg.tools) targetMsg.tools = []
            targetMsg.tools.push({
              id: 'tool_' + Date.now() + Math.random(),
              name: toolName,
              input: inputArgs,
              status: 'running',
            })
          },
          // 收到工具调用结束及执行结果
          onToolEnd: (toolName, outputResult) => {
            if (targetMsg.tools) {
              const tool = [...targetMsg.tools].reverse().find(t => t.name === toolName && t.status === 'running')
              if (tool) {
                tool.output = outputResult
                tool.status = 'completed'
              }
            }
          },
          // 收到工具调用执行失败或异常
          onToolError: (toolName, errorMsg) => {
            if (targetMsg.tools) {
              const tool = [...targetMsg.tools].reverse().find(t => t.name === toolName && t.status === 'running')
              if (tool) {
                tool.output = errorMsg || '工具执行遇到异常'
                tool.status = 'error'
              }
            }
          },
          // 收到模型动态路由分流通知
          onModelRouted: (info) => {
            targetMsg.routedModel = info
          },
          // 收到长程任务规划清单更新
          onPlan: (plan) => {
            targetMsg.plan = plan
          },
          // LangGraph 节点变化
          onNodeChange: (nodeName) => {
            targetMsg.currentNode = nodeName
          },
          // 错误处理：确保所有未完成的工具全部终止转圈并标记状态
          onError: (errMsg, hint) => {
            if (thoughtStartTime && !thoughtEndTime) {
              thoughtEndTime = Date.now()
              targetMsg.thoughtDuration = Math.max(0.1, Number(((thoughtEndTime - thoughtStartTime) / 1000).toFixed(1)))
            }
            targetMsg.error = errMsg + (hint ? ` (${hint})` : '')
            targetMsg.isStreaming = false
            if (targetMsg.tools) {
              for (const t of targetMsg.tools) {
                if (t.status === 'running') {
                  t.status = 'error'
                  if (!t.output) {
                    t.output = `执行异常中断: ${errMsg}`
                  }
                }
              }
            }
            this.isGenerating = false
            this.saveSessions()
          },
          // 生成完成：收敛任何残留的 running 状态并检测敏感操作确认请求
          onDone: () => {
            if (thoughtStartTime && !thoughtEndTime) {
              thoughtEndTime = Date.now()
              targetMsg.thoughtDuration = Math.max(0.1, Number(((thoughtEndTime - thoughtStartTime) / 1000).toFixed(1)))
            } else if (!targetMsg.thoughtDuration && targetMsg.thought) {
              targetMsg.thoughtDuration = Math.max(0.1, Number(((Date.now() - assistantMsg.timestamp) / 1000).toFixed(1)))
            }
            targetMsg.isStreaming = false
            if (targetMsg.tools) {
              for (const t of targetMsg.tools) {
                if (t.status === 'running') {
                  t.status = 'completed'
                  if (!t.output) {
                    t.output = '执行完毕'
                  }
                }
              }
            }
            this.isGenerating = false

            // 检测是否存在待用户确认的敏感/删除操作并挂载到当前消息
            const parsedApproval = parseApprovalData(targetMsg.content)
            if (parsedApproval && !targetMsg.approvalStatus) {
              targetMsg.approvalData = parsedApproval
              targetMsg.approvalStatus = 'pending'
            }

            this.saveSessions()
          },
        }
      )
    },

    /** 确认并执行待批准的敏感操作 (支持人在回路参数修改放行) */
    async approveOperation(messageId: string, rememberSimilar: boolean = false, customTarget?: string) {
      const msg = this.messages.find(m => m.id === messageId)
      if (!msg || !msg.approvalData || this.isGenerating) return

      msg.approvalStatus = 'approved'
      const target = (customTarget !== undefined && customTarget.trim() !== '') ? customTarget.trim() : (msg.approvalData.target || '')
      const settings = useSettingsStore()

      if (rememberSimilar) {
        // 用户勾选“允许类似命令”，智能放宽本会话的执行权限
        settings.setApprovalMode('full_access')
      }

      // 静默授权指令，提示大模型直接调用工具并汇报真实结果，严禁输出任何“好的”、“已确认”等客套开场白
      const silentPrompt = customTarget && customTarget.trim() !== msg.approvalData.target
        ? `[系统授权指令] 用户已审阅并修改了参数，允许执行修改后的操作：${target}。请直接调用对应工具执行此项修改后的操作，严禁在回复中输出任何“已确认”、“好的”、“收到”等客套开场白，直接调用工具并在完成后汇报真实结果。`
        : `[系统授权指令] 用户已通过操作卡片允许执行该操作：${target}。请直接调用对应工具执行真实操作，严禁在回复中输出任何“已确认”、“好的”、“收到”等客套开场白，直接调用工具并在完成后汇报真实结果。`

      msg.isStreaming = true
      this.isGenerating = true
      this.saveSessions()

      let hasAppendedSeparator = false
      let pendingBuffer = ''

      await sseClient.streamChat(
        {
          message: silentPrompt,
          session_id: this.currentSessionId,
          mode: this.activeMode,
          model: settings.model,
          base_url: settings.baseUrl,
          api_key: settings.apiKey,
          temperature: settings.temperature,
          approval_mode: settings.approvalMode,
        },
        {
          onToken: (token) => {
            if (!hasAppendedSeparator) {
              pendingBuffer += token
              // 自动清洗可能产生的“好的，已确认为您执行...”等多余开场白
              const cleaned = pendingBuffer.replace(/^(?:好的[，,！!]?)?\s*(?:已确认|确认执行|好的|收到)[，,！!。\s]*/i, '')
              if (pendingBuffer.length > 20 || cleaned.length > 0) {
                hasAppendedSeparator = true
                if (cleaned) {
                  msg.content = (msg.content ? msg.content.trim() + '\n\n' : '') + cleaned
                }
              }
              return
            }
            msg.content += token
          },
          onThought: (thought) => {
            msg.thought = (msg.thought || '') + thought
          },
          onToolStart: (toolName, inputArgs) => {
            if (!msg.tools) msg.tools = []
            msg.tools.push({
              id: 'tool_' + Date.now() + Math.random(),
              name: toolName,
              input: inputArgs,
              status: 'running',
            })
          },
          onToolEnd: (toolName, outputResult) => {
            if (msg.tools) {
              const currentTool = [...msg.tools].reverse().find(t => t.name === toolName && t.status === 'running')
              if (currentTool) {
                currentTool.status = 'completed'
                currentTool.output = outputResult
              }
            }
          },
          onToolError: (toolName, errorMsg) => {
            if (msg.tools) {
              const currentTool = [...msg.tools].reverse().find(t => t.name === toolName && t.status === 'running')
              if (currentTool) {
                currentTool.status = 'error'
                currentTool.output = errorMsg
              }
            }
          },
          onNodeChange: () => {},
          onError: (errorMsg) => {
            msg.error = errorMsg
            msg.isStreaming = false
            this.isGenerating = false
            this.saveSessions()
          },
          onDone: () => {
            if (!hasAppendedSeparator && pendingBuffer) {
              const cleaned = pendingBuffer.replace(/^(?:好的[，,！!]?)?\s*(?:已确认|确认执行|好的|收到)[，,！!。\s]*/i, '').trim()
              if (cleaned) {
                msg.content = (msg.content ? msg.content.trim() + '\n\n' : '') + cleaned
              }
            }
            msg.isStreaming = false
            this.isGenerating = false
            this.saveSessions()
            if (typeof window !== 'undefined') {
              window.dispatchEvent(new CustomEvent('scroll-chat-to-bottom'))
              setTimeout(() => window.dispatchEvent(new CustomEvent('scroll-chat-to-bottom')), 80)
            }
          },
        }
      )
    },

    /** 拒绝并取消待批准的敏感操作 (静默无感执行，绝不在对话中生成多余用户气泡) */
    async rejectOperation(messageId: string) {
      const msg = this.messages.find(m => m.id === messageId)
      if (!msg || !msg.approvalData || this.isGenerating) return

      msg.approvalStatus = 'rejected'
      const target = msg.approvalData.target || ''
      const settings = useSettingsStore()

      const silentPrompt = `[系统指令] 用户已通过操作卡片拒绝执行该操作：${target}。该操作已取消，请保持原状，简明反馈操作已取消即可，严禁冗长赘述。`

      msg.isStreaming = true
      this.isGenerating = true
      this.saveSessions()

      let hasAppendedSeparator = false
      let pendingBuffer = ''

      await sseClient.streamChat(
        {
          message: silentPrompt,
          session_id: this.currentSessionId,
          mode: this.activeMode,
          model: settings.model,
          base_url: settings.baseUrl,
          api_key: settings.apiKey,
          temperature: settings.temperature,
          approval_mode: settings.approvalMode,
        },
        {
          onToken: (token) => {
            if (!hasAppendedSeparator) {
              pendingBuffer += token
              const cleaned = pendingBuffer.replace(/^(?:好的[，,！!]?)?\s*(?:已确认|确认执行|好的|收到)[，,！!。\s]*/i, '')
              if (pendingBuffer.length > 20 || cleaned.length > 0) {
                hasAppendedSeparator = true
                if (cleaned) {
                  msg.content = (msg.content ? msg.content.trim() + '\n\n' : '') + cleaned
                }
              }
              return
            }
            msg.content += token
          },
          onThought: (thought) => {
            msg.thought = (msg.thought || '') + thought
          },
          onToolStart: () => {},
          onToolEnd: () => {},
          onNodeChange: () => {},
          onError: () => {
            msg.isStreaming = false
            this.isGenerating = false
            this.saveSessions()
          },
          onDone: () => {
            if (!hasAppendedSeparator && pendingBuffer) {
              const cleaned = pendingBuffer.replace(/^(?:好的[，,！!]?)?\s*(?:已确认|确认执行|好的|收到)[，,！!。\s]*/i, '').trim()
              if (cleaned) {
                msg.content = (msg.content ? msg.content.trim() + '\n\n' : '') + cleaned
              }
            }
            msg.isStreaming = false
            this.isGenerating = false
            this.saveSessions()
            if (typeof window !== 'undefined') {
              window.dispatchEvent(new CustomEvent('scroll-chat-to-bottom'))
              setTimeout(() => window.dispatchEvent(new CustomEvent('scroll-chat-to-bottom')), 80)
            }
          },
        }
      )
    },

    /** 手动中止当前的流式生成 */
    stopGeneration() {
      sseClient.abort()
      this.isGenerating = false
      const lastMsg = this.messages[this.messages.length - 1]
      if (lastMsg) {
        lastMsg.isStreaming = false
        if (lastMsg.tools) {
          for (const t of lastMsg.tools) {
            if (t.status === 'running') {
              t.status = 'error'
              if (!t.output) {
                t.output = '用户已手动中止生成'
              }
            }
          }
        }
      }
      this.saveSessions()
    },
  },
})
