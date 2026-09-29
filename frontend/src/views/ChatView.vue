<script setup lang="ts">
/**
 * 对话工作台视图 (ChatView) - Codex 现代排版风格
 * 1. Agent 模式选择与当前模型指示均移至输入框上方紧凑控制栏，视线高度聚焦。
 * 2. 模型支持点击弹出快速切换菜单与管理设置直达。
 * 3. 顶部简化为清爽无干扰的会话状态栏与新会话入口。
 */
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import {
  Send,
  Square,
  Bot,
  BookOpen,
  Search,
  Code2,
  FileText,
  Plus,
  Trash2,
  ChevronDown,
  Check,
  Sliders,
  ArrowUp,
  ArrowDown,
  Hand,
  ShieldCheck,
  AlertTriangle,
  FileCode,
  X as XIcon,
  Loader2,
  Download,
  SquareTerminal,
  CornerDownLeft,
  Info,
  Folder,
  Printer,
  Pencil,
  Zap,
} from 'lucide-vue-next'
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'
import { apiClient } from '../api/client'
import ChatMessage from '../components/ChatMessage.vue'

const chatStore = useChatStore()
const settingsStore = useSettingsStore()

// 用户输入内容
const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

// 动态高度自适应：根据输入内容或多行粘贴平滑伸缩（44px ~ 180px）
const adjustTextareaHeight = () => {
  nextTick(() => {
    if (!textareaRef.value) return
    textareaRef.value.style.height = 'auto'
    const scrollH = textareaRef.value.scrollHeight
    const targetH = Math.min(Math.max(scrollH, 44), 180)
    textareaRef.value.style.height = `${targetH}px`
    textareaRef.value.style.overflowY = scrollH > 180 ? 'auto' : 'hidden'
  })
}

watch(inputText, () => {
  adjustTextareaHeight()
})

// 将当前对话完整导出为排版精美的 Markdown (.md) 文件
const exportConversationMarkdown = () => {
  if (chatStore.messages.length === 0) return

  const title = currentSessionTitle.value || '对话记录'
  const dateStr = new Date().toISOString().slice(0, 10)
  const lines: string[] = [
    `# ${title}`,
    `> 导出时间: ${new Date().toLocaleString()}`,
    `> 运行模式: ${chatStore.activeMode}`,
    '',
    '---',
    '',
  ]

  for (const m of chatStore.messages) {
    if (m.role === 'user') {
      lines.push(`### 🧑 用户`)
      if (m.docs && m.docs.length > 0) {
        lines.push(`*附件文档: ${m.docs.map(d => d.name).join(', ')}*`)
      }
      lines.push('')
      lines.push(m.content || '')
      lines.push('')
    } else if (m.role === 'assistant') {
      lines.push(`### 🤖 智能助手`)
      if (m.thought) {
        lines.push('<details><summary>思考过程</summary>')
        lines.push('')
        lines.push(m.thought)
        lines.push('')
        lines.push('</details>')
        lines.push('')
      }
      if (m.tools && m.tools.length > 0) {
        lines.push(`<details><summary>工具执行记录 (${m.tools.length} 项)</summary>`)
        lines.push('')
        for (const t of m.tools) {
          lines.push(`- **${t.name}** [${t.status}]`)
          if (t.output) {
            lines.push('```')
            lines.push(t.output)
            lines.push('```')
          }
        }
        lines.push('')
        lines.push('</details>')
        lines.push('')
      }
      lines.push(m.content || '')
      lines.push('')
    }
    lines.push('---')
    lines.push('')
  }

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title.replace(/[\/\\?%*:|"<>]/g, '_')}_${dateStr}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// 导出 JSON 结构化数据
const exportConversationJSON = () => {
  if (chatStore.messages.length === 0) return
  showExportMenu.value = false
  const title = currentSessionTitle.value || '对话记录'
  const dateStr = new Date().toISOString().slice(0, 10)
  const data = {
    title,
    mode: chatStore.activeMode,
    exportedAt: new Date().toISOString(),
    messages: chatStore.messages,
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title.replace(/[\/\\?%*:|"<>]/g, '_')}_${dateStr}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// 打印 / 导出为 PDF
const printConversationPDF = () => {
  showExportMenu.value = false
  window.print()
}

// 导出菜单状态
const showExportMenu = ref(false)
const exportMenuRef = ref<HTMLElement | null>(null)

// 人在回路：参数/指令就地修改状态
const isEditingApprovalTarget = ref(false)
const editedApprovalTarget = ref('')

const toggleEditApprovalTarget = () => {
  if (!isEditingApprovalTarget.value) {
    editedApprovalTarget.value = pendingApprovalMessage.value?.approvalData?.target || ''
    isEditingApprovalTarget.value = true
  } else {
    isEditingApprovalTarget.value = false
  }
}

// 滚动容器引用
const scrollContainer = ref<HTMLElement | null>(null)
// 是否显示输入框上方模型快捷切换下拉面板
const showModelDropdown = ref(false)
// 模型下拉触发容器引用
const modelDropdownRef = ref<HTMLElement | null>(null)

// 是否显示操作批准权限下拉面板
const showApprovalDropdown = ref(false)
// 权限下拉触发容器引用
const approvalDropdownRef = ref<HTMLElement | null>(null)

// 快速切换操作批准权限模式
const selectApprovalMode = (mode: 'ask_always' | 'smart' | 'full_access') => {
  settingsStore.setApprovalMode(mode)
  showApprovalDropdown.value = false
}

// 统一全能自主智能体，默认固定为 react 模式
chatStore.activeMode = 'react'

// 当前会话标题
const currentSessionTitle = computed(() => {
  const current = chatStore.sessions.find(s => s.id === chatStore.currentSessionId)
  return current ? current.title : '新对话'
})

// 当前服务商下可供快速选择的模型清单
const availableQuickModels = computed(() => {
  const models = settingsStore.currentModels
  if (models && models.length > 0) {
    return models
  }
  // 未拉取时，至少提供当前已设定的模型
  return [{ id: settingsStore.model, name: settingsStore.model }]
})

// 快速切换当前使用的模型
const selectQuickModel = (modelId: string) => {
  settingsStore.setModel(modelId)
  showModelDropdown.value = false
}

// 是否处于跟随最新消息自动吸底状态（默认开启）
const shouldAutoScroll = ref(true)
const messagesListRef = ref<HTMLElement | null>(null)

// 标记当前是否处于会话切换阶段（阻断切换期间因 DOM 变更触发的 transient scroll 误覆盖）
const isSwitchingSession = ref(false)

// 自动滚动到消息流底部（支持平滑与多阶段渲染高度补正）
const scrollToBottom = async (smooth = false) => {
  await nextTick()
  if (!scrollContainer.value) return

  if (smooth) {
    scrollToBottomSmooth()
  } else {
    scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
  }

  // 多阶段延时校准：确保卡片操作、折叠展开、Markdown 高亮、KaTeX 渲染完成后精准触底
  setTimeout(() => {
    if (scrollContainer.value && (shouldAutoScroll.value || chatStore.isGenerating)) {
      if (!smooth) {
        scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
      } else {
        scrollToBottomSmooth()
      }
    }
  }, 60)
  setTimeout(() => {
    if (scrollContainer.value && (shouldAutoScroll.value || chatStore.isGenerating)) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    }
  }, 180)
}

// ==========================================
// 动态高度虚拟滚动引擎 (Dynamic Variable-Height Virtual Scroll)
// 当单会话消息数较多 (> 20 条) 时自动开启视口裁剪，屏幕外 DOM 自动移出，保持 60fps 丝滑吸底
// ==========================================
const VIRTUAL_SCROLL_THRESHOLD = 20
const BUFFER_PX = 1200
const ESTIMATED_ITEM_HEIGHT = 140

const measuredHeights = new Map<string, number>()
const visibleStartIndex = ref(0)
const visibleEndIndex = ref(0)
const topSpacerHeight = ref(0)
const bottomSpacerHeight = ref(0)

const isVirtualScrollActive = computed(() => {
  return chatStore.messages.length > VIRTUAL_SCROLL_THRESHOLD
})

const updateVirtualWindow = () => {
  const msgs = chatStore.messages
  if (!msgs || msgs.length <= VIRTUAL_SCROLL_THRESHOLD || !scrollContainer.value) {
    visibleStartIndex.value = 0
    visibleEndIndex.value = msgs.length - 1
    topSpacerHeight.value = 0
    bottomSpacerHeight.value = 0
    return
  }

  const scrollTop = scrollContainer.value.scrollTop
  const clientHeight = scrollContainer.value.clientHeight
  const viewportTop = Math.max(0, scrollTop - BUFFER_PX)
  const viewportBottom = scrollTop + clientHeight + BUFFER_PX

  let accumulated = 0
  let start = -1
  let end = msgs.length - 1
  let topHeight = 0
  let bottomHeight = 0

  for (let i = 0; i < msgs.length; i++) {
    const id = msgs[i].id
    const h = measuredHeights.get(id) || ESTIMATED_ITEM_HEIGHT
    const itemTop = accumulated
    const itemBottom = accumulated + h

    if (start === -1) {
      if (itemBottom >= viewportTop) {
        start = i
        topHeight = itemTop
      }
    }

    if (itemTop > viewportBottom) {
      end = i
      for (let j = i; j < msgs.length; j++) {
        bottomHeight += (measuredHeights.get(msgs[j].id) || ESTIMATED_ITEM_HEIGHT)
      }
      break
    }

    accumulated += h
  }

  if (start === -1) start = 0

  // 保证正在生成阶段或吸底跟随状态时，底部消息始终处于渲染树中并完美吸底
  if (chatStore.isGenerating || shouldAutoScroll.value) {
    end = msgs.length - 1
    bottomHeight = 0
  }

  visibleStartIndex.value = Math.max(0, start)
  visibleEndIndex.value = Math.min(msgs.length - 1, end)
  topSpacerHeight.value = topHeight
  bottomSpacerHeight.value = bottomHeight
}

const recordMessageHeight = (id: string, el: HTMLElement | null) => {
  if (el) {
    const h = el.offsetHeight
    if (h > 0 && measuredHeights.get(id) !== h) {
      measuredHeights.set(id, h)
    }
  }
}

const displayedMessages = computed(() => {
  const msgs = chatStore.messages
  if (msgs.length <= VIRTUAL_SCROLL_THRESHOLD) {
    return msgs
  }
  return msgs.slice(visibleStartIndex.value, visibleEndIndex.value + 1)
})

// ========================
// 1. 回到底部悬浮控制 (丝滑平滑下滚) 与各会话独立滚动位置记忆
// ========================
const showScrollBottomBtn = ref(false)

const handleScroll = () => {
  if (!scrollContainer.value) return
  const { scrollTop, scrollHeight, clientHeight } = scrollContainer.value
  const distanceToBottom = scrollHeight - scrollTop - clientHeight

  // 当距离底部在 120px 以内时，用户处于“正在看最新消息”状态，保持自动吸底
  // 当用户向上翻阅超过 120px 时，暂停自动吸底，保护用户阅读历史不被打扰
  const isAtBottom = distanceToBottom < 120
  shouldAutoScroll.value = isAtBottom

  // 当距离底部超过 100px 时显示“回到底部”悬浮按钮
  showScrollBottomBtn.value = distanceToBottom > 100

  // 仅在正常浏览会话时实时记录该会话的真实滚动位置；在切换会话装载 DOM 期间不记录
  if (!isSwitchingSession.value && chatStore.currentSessionId) {
    chatStore.saveSessionScroll(chatStore.currentSessionId, scrollTop, isAtBottom)
  }

  // 触发动态虚拟滚动窗口计算
  updateVirtualWindow()
}

const scrollToBottomSmooth = () => {
  if (!scrollContainer.value) return
  shouldAutoScroll.value = true
  const el = scrollContainer.value
  const start = el.scrollTop
  let end = el.scrollHeight - el.clientHeight
  const distance = end - start
  if (distance <= 0) return

  // 极速丝滑平滑下滚：采用 easeOutCubic 极速启动、柔和停靠
  const duration = Math.min(240, Math.max(120, Math.abs(distance) * 0.12))
  const startTime = performance.now()

  const step = (now: number) => {
    if (!scrollContainer.value) return
    // 动态获取最新的 scrollHeight，防止生成中或卡片展开导致目标终点过时
    end = el.scrollHeight - el.clientHeight
    const elapsed = now - startTime
    const progress = Math.min(elapsed / duration, 1)
    const ease = 1 - Math.pow(1 - progress, 3)
    el.scrollTop = start + (end - start) * ease
    if (progress < 1) {
      requestAnimationFrame(step)
    } else {
      el.scrollTop = end
      if (chatStore.currentSessionId) {
        chatStore.saveSessionScroll(chatStore.currentSessionId, end, true)
      }
    }
  }
  requestAnimationFrame(step)
}

// 恢复指定会话的历史滚动位置，保证各会话滚动状态互不影响
const restoreSessionScroll = (sessionId: string) => {
  if (!scrollContainer.value) {
    isSwitchingSession.value = false
    return
  }

  const saved = chatStore.getSessionScroll(sessionId)

  // 1. 首次进入该会话（无滚动记忆）：默认吸底查看最新消息
  if (!saved) {
    shouldAutoScroll.value = true
    scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    setTimeout(() => {
      if (scrollContainer.value && chatStore.currentSessionId === sessionId) {
        scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
        isSwitchingSession.value = false
      }
    }, 60)
    return
  }

  // 2. 该会话之前处于“已吸底”状态（正看最新消息）：恢复吸底
  if (saved.isAtBottom) {
    shouldAutoScroll.value = true
    scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    setTimeout(() => {
      if (scrollContainer.value && chatStore.currentSessionId === sessionId) {
        scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
        isSwitchingSession.value = false
      }
    }, 60)
  } else {
    // 3. 用户之前在翻阅历史（非吸底）：精准还原到上次停留的 scrollTop！
    shouldAutoScroll.value = false
    scrollContainer.value.scrollTop = saved.scrollTop

    // 延迟多阶段校准：防止富文本/图片异步排版撑开高度后产生微偏移
    setTimeout(() => {
      if (scrollContainer.value && chatStore.currentSessionId === sessionId) {
        scrollContainer.value.scrollTop = saved.scrollTop
        isSwitchingSession.value = false
      }
    }, 60)
    setTimeout(() => {
      if (scrollContainer.value && chatStore.currentSessionId === sessionId) {
        scrollContainer.value.scrollTop = saved.scrollTop
        isSwitchingSession.value = false
      }
    }, 180)
  }
}

// 监听会话切换：在切换离开旧会话前记录旧位置，切换到新会话后精准还原新位置
watch(
  () => chatStore.currentSessionId,
  async (newSessionId, oldSessionId) => {
    // 离开旧会话前保存旧会话真实的滚动位置
    if (oldSessionId && scrollContainer.value && !isSwitchingSession.value) {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer.value
      const isAtBottom = (scrollHeight - scrollTop - clientHeight) < 120
      chatStore.saveSessionScroll(oldSessionId, scrollTop, isAtBottom)
    }

    if (!newSessionId) return

    // 开启会话切换锁，防止切换过程中的 DOM 瞬变误触发滚动保存与吸底重置
    isSwitchingSession.value = true
    await nextTick()
    restoreSessionScroll(newSessionId)
  }
)

// 深度监听所有触发页面高度变化的消息状态（消息增减、正文流式输出、思考链、工具调用列表、工具输出结果、审批状态变动、错误产生）
watch(
  () => {
    const msgs = chatStore.messages
    const last = msgs[msgs.length - 1]
    if (!last) return [msgs.length]
    return [
      msgs.length,
      last.content?.length || 0,
      last.thought?.length || 0,
      last.tools?.length || 0,
      last.tools?.map((t) => `${t.status}_${t.output?.length || 0}`).join('|'),
      last.approvalStatus,
      last.error,
    ]
  },
  () => {
    // 正在切换会话时，由 restoreSessionScroll 全权负责定位，严禁触发 scrollToBottom 导致历史翻阅位置丢失
    if (isSwitchingSession.value) return

    if (shouldAutoScroll.value || chatStore.isGenerating) {
      scrollToBottom()
    }
  },
  { deep: true }
)

// 响应全局卡片操作或用户确认执行后的强制回到底部事件
const handleGlobalScrollToBottom = () => {
  shouldAutoScroll.value = true
  scrollToBottom(true)
}

// ========================
// 2. 输入历史按上下键切换记录
// ========================
const inputHistory = ref<string[]>(JSON.parse(localStorage.getItem('agent_input_history') || '[]'))
const historyIndex = ref(-1)
const tempDraft = ref('')

// ========================
// 3. 多模态图片与文档附件上传支持
// ========================
interface AttachedDoc {
  id: string
  name: string
  size: number
  content: string
  isPdf?: boolean
  pages?: number
  loading?: boolean
}

const attachedImages = ref<string[]>([])
const attachedDocs = ref<AttachedDoc[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const isDraggingOver = ref(false)

const triggerFileInput = () => {
  fileInputRef.value?.click()
}

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const readFileAsBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = (err) => reject(err)
    reader.readAsDataURL(file)
  })
}

// 判断是否为 PDF 文档
const isPdfFile = (file: File) => {
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  return file.type === 'application/pdf' || ext === 'pdf'
}

// 判断是否为支持的代码或文本文档
const isCodeOrTextFile = (file: File) => {
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  const textExtensions = [
    'txt', 'md', 'markdown', 'json', 'csv', 'tsv', 'xml', 'yaml', 'yml',
    'py', 'js', 'ts', 'jsx', 'tsx', 'html', 'css', 'scss', 'vue',
    'sh', 'bash', 'zsh', 'sql', 'c', 'cpp', 'h', 'java', 'go', 'rs', 'php',
    'log', 'env', 'toml', 'ini', 'dockerfile'
  ]
  return file.type.startsWith('text/') || textExtensions.includes(ext)
}

// 统一解析上传的文件（图片 -> base64 多模态；PDF -> 后端解析纯文本与页码；代码/文档 -> 纯文本解析）
const processUploadedFile = async (file: File) => {
  if (file.type.startsWith('image/')) {
    try {
      const b64 = await readFileAsBase64(file)
      attachedImages.value.push(b64)
    } catch (err) {
      console.error('读取图片失败', err)
    }
  } else if (isPdfFile(file)) {
    const docId = 'doc_' + Date.now() + Math.random().toString(36).substring(2, 7)
    const tempDoc: AttachedDoc = {
      id: docId,
      name: file.name,
      size: file.size,
      content: '',
      isPdf: true,
      loading: true,
    }
    attachedDocs.value.push(tempDoc)
    try {
      const res = await apiClient.parseChatFile(file)
      const target = attachedDocs.value.find(d => d.id === docId)
      if (target) {
        target.content = res.text
        target.pages = res.pages
        target.loading = false
      }
    } catch (err: any) {
      console.error('解析 PDF 失败', err)
      const target = attachedDocs.value.find(d => d.id === docId)
      if (target) {
        target.content = `[PDF 解析失败: ${err?.message || '未知错误'}]`
        target.loading = false
      }
    }
  } else if (isCodeOrTextFile(file)) {
    try {
      const text = await file.text()
      attachedDocs.value.push({
        id: 'doc_' + Date.now() + Math.random().toString(36).substring(2, 7),
        name: file.name,
        size: file.size,
        content: text,
        isPdf: false,
        pages: 1,
      })
    } catch (err) {
      console.error('读取文档失败', err)
    }
  }
}

const handleFileSelect = async (e: Event) => {
  const target = e.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return
  for (let i = 0; i < target.files.length; i++) {
    await processUploadedFile(target.files[i])
  }
  target.value = ''
}

const handlePaste = async (e: ClipboardEvent) => {
  const items = e.clipboardData?.items
  if (!items) return

  let hasFile = false
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) {
        hasFile = true
        await processUploadedFile(file)
      }
    }
  }
  if (hasFile) {
    e.preventDefault()
  }
}

const handleDragOver = (e: DragEvent) => {
  e.preventDefault()
  isDraggingOver.value = true
}

const handleDragLeave = (e: DragEvent) => {
  e.preventDefault()
  isDraggingOver.value = false
}

const handleDrop = async (e: DragEvent) => {
  e.preventDefault()
  isDraggingOver.value = false
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

  for (let i = 0; i < files.length; i++) {
    await processUploadedFile(files[i])
  }
}

const removeAttachedImage = (index: number) => {
  attachedImages.value.splice(index, 1)
}

const removeAttachedDoc = (index: number) => {
  attachedDocs.value.splice(index, 1)
}

// 发送用户消息 (支持文本、代码文档附件及多模态图片)
const handleSend = () => {
  const trimmed = inputText.value.trim()
  const hasImages = attachedImages.value.length > 0
  const hasDocs = attachedDocs.value.length > 0
  if ((!trimmed && !hasImages && !hasDocs) || chatStore.isGenerating) return

  // 若文档仍在解析中则暂缓发送
  if (attachedDocs.value.some(d => d.loading)) return

  // 拼接文档附件内容供智能体直接理解与分析（结构化隔离用户指令与参考文档，防范大模型把简短提问当作标题机械复述）
  let promptToSend = trimmed
  if (hasDocs) {
    const docSections = attachedDocs.value.map(d => {
      const typeLabel = d.isPdf ? `PDF文档(${d.pages || 1}页)` : '文档/代码'
      return `【用户上传${typeLabel}: ${d.name} (${formatFileSize(d.size)})】\n\`\`\`\n${d.content}\n\`\`\``
    }).join('\n\n')

    if (trimmed) {
      promptToSend = `【用户提问与指令】\n${trimmed}\n\n【用户上传参考文档】（请直接依据此文档按上述指令作答，开门见山输出分析，严禁在开头机械复述或输出“${trimmed}”）：\n\n${docSections}`
    } else {
      promptToSend = `【用户上传参考文档】（请直接查阅并分析下述文档，开门见山给出摘要与核心解析）：\n\n${docSections}`
    }
  }

  // 记录输入历史
  if (trimmed) {
    if (inputHistory.value[inputHistory.value.length - 1] !== trimmed) {
      inputHistory.value.push(trimmed)
      if (inputHistory.value.length > 60) inputHistory.value.shift()
      localStorage.setItem('agent_input_history', JSON.stringify(inputHistory.value))
    }
  }
  historyIndex.value = -1
  tempDraft.value = ''

  const imgs = [...attachedImages.value]
  const docsMeta = attachedDocs.value.map(d => ({
    name: d.name,
    size: d.size,
    isPdf: d.isPdf,
    pages: d.pages,
  }))

  inputText.value = ''
  attachedImages.value = []
  attachedDocs.value = []
  adjustTextareaHeight()
  shouldAutoScroll.value = true
  chatStore.sendMessage(trimmed, imgs, docsMeta, promptToSend)
  scrollToBottom(true)
}

// 标记是否正处于中文/输入法候选词合成输入状态 (IME Composition)
const isComposing = ref(false)

const handleCompositionStart = () => {
  isComposing.value = true
}

const handleCompositionEnd = () => {
  // macOS / Chromium 下选词完成时 Enter 事件可能紧随 compositionend 触发，
  // 延迟 50ms 释放状态，彻底阻断输入法回车确认时的误触发送
  setTimeout(() => {
    isComposing.value = false
  }, 50)
}

// 快捷键监听：Enter 发送，Shift+Enter 换行，ArrowUp/ArrowDown 切换输入历史
const handleKeyDown = (e: KeyboardEvent) => {
  // 1. 若当前正处于中文输入法拼音选词合成中，或是输入法专用的 229 按键码，拦截发送
  if (e.isComposing || isComposing.value || e.keyCode === 229) {
    return
  }

  const textarea = e.target as HTMLTextAreaElement

  // 2. 方向键上：切换上一条历史输入
  if (e.key === 'ArrowUp') {
    const isAtBeginning = textarea.selectionStart === 0 && textarea.selectionEnd === 0
    if ((isAtBeginning || !inputText.value) && inputHistory.value.length > 0) {
      e.preventDefault()
      if (historyIndex.value === -1) {
        tempDraft.value = inputText.value
        historyIndex.value = inputHistory.value.length - 1
      } else if (historyIndex.value > 0) {
        historyIndex.value--
      }
      inputText.value = inputHistory.value[historyIndex.value] || ''
      nextTick(() => {
        textarea.selectionStart = textarea.selectionEnd = textarea.value.length
      })
      return
    }
  }

  // 3. 方向键下：切换下一条历史输入或还原草稿
  if (e.key === 'ArrowDown') {
    const isAtEnd = textarea.selectionStart === textarea.value.length
    if ((isAtEnd || !inputText.value) && historyIndex.value !== -1) {
      e.preventDefault()
      if (historyIndex.value < inputHistory.value.length - 1) {
        historyIndex.value++
        inputText.value = inputHistory.value[historyIndex.value]
      } else {
        historyIndex.value = -1
        inputText.value = tempDraft.value
      }
      nextTick(() => {
        textarea.selectionStart = textarea.selectionEnd = textarea.value.length
      })
      return
    }
  }

  // 4. 只有正常按下独立回车（非 Shift+Enter）时触发提交
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// 应用预置的推荐引导提示词
const applyPromptSuggestion = (text: string) => {
  inputText.value = text
  handleSend()
}

// 清空当前对话记录
const handleClearChat = () => {
  if (confirm('确认清空当前对话的消息记录吗？')) {
    chatStore.clearCurrentSessionMessages()
  }
}

// ========================
// 待审批操作直接在输入框区域展示与交互（对标 Cursor / Claude Code 官方体验）
// ========================
const isPendingApprovalMenuOpen = ref(false)

const pendingApprovalMessage = computed(() => {
  return [...chatStore.messages].reverse().find(
    m => m.approvalData && (!m.approvalStatus || m.approvalStatus === 'pending')
  ) || null
})

const isPendingTerminalAction = computed(() => {
  const data = pendingApprovalMessage.value?.approvalData
  if (!data) return false
  return data.action === 'execute_terminal_command' ||
         data.action === 'execute_command' ||
         data.type === '终端' ||
         Boolean(data.type && data.type.includes('终端')) ||
         Boolean(data.target && /mkdir|rm|git|npm|python|bash|sh|ls|curl|chmod|pnpm|yarn/i.test(data.target))
})

const isPendingDeleteAction = computed(() => {
  const data = pendingApprovalMessage.value?.approvalData
  if (!data) return false
  return data.action === 'delete_file' ||
         data.action === 'delete_local_file' ||
         Boolean(data.type && data.type.includes('删除'))
})

const isPendingFolderAction = computed(() => {
  const data = pendingApprovalMessage.value?.approvalData
  if (!data) return false
  return Boolean(data.type && (data.type.includes('目录') || data.type.includes('文件夹'))) ||
         Boolean(data.target && data.target.includes('mkdir'))
})

const pendingApprovalCategoryName = computed(() => {
  const data = pendingApprovalMessage.value?.approvalData
  if (!data) return '终端'
  if (data.type && data.type !== '操作类型' && data.type !== '系统操作') {
    return data.type
  }
  if (isPendingTerminalAction.value) return '终端'
  if (isPendingDeleteAction.value || isPendingFolderAction.value) return '文件系统'
  return '终端'
})

const pendingApprovalQuestion = computed(() => {
  const data = pendingApprovalMessage.value?.approvalData
  if (!data) return ''
  let q = (data.title || '').trim()
  const target = (data.target || '').trim()

  // 1. 优先提取 mkdir 创建文件夹意图与文件夹名 (如: mkdir -p ~/Desktop/55 -> 允许我在桌面创建名为“55”的文件夹吗？)
  if (target.includes('mkdir')) {
    const parts = target.split(/\s+/).filter(p => !p.startsWith('-') && p !== 'mkdir')
    const pathStr = parts.pop()?.replace(/["']/g, '') || ''
    const folderName = pathStr.split('/').filter(Boolean).pop() || ''
    const isDesktop = target.toLowerCase().includes('desktop') || target.includes('桌面')
    if (folderName) {
      return isDesktop
        ? `允许我在桌面创建名为“${folderName}”的文件夹吗？`
        : `允许我创建名为“${folderName}”的文件夹吗？`
    }
  }

  // 2. 如果原始标题已经是具体的非通用提问（不包含“此终端命令”等宽泛指代）
  if (/[吗\?？]$/.test(q) && !q.includes('此终端命令') && !q.includes('敏感操作') && !q.includes('待执行')) {
    return q
  }

  // 3. 删除文件意图
  const fileName = target.split('/').filter(Boolean).pop()?.replace(/["']/g, '') || target
  if (isPendingDeleteAction.value) {
    return fileName ? `允许我永久删除“${fileName}”吗？` : '允许我删除该文件吗？'
  }

  // 4. 终端命令与通用操作兜底
  if (isPendingTerminalAction.value) {
    return '允许我执行此终端命令吗？'
  }
  return q ? `${q}吗？` : '允许执行此操作吗？'
})

const handleApprovePendingApproval = (rememberSimilar: boolean = false) => {
  if (!pendingApprovalMessage.value) return
  isPendingApprovalMenuOpen.value = false
  const msgId = pendingApprovalMessage.value.id
  const customTarget = isEditingApprovalTarget.value ? editedApprovalTarget.value.trim() : undefined
  chatStore.approveOperation(msgId, rememberSimilar, customTarget)
  isEditingApprovalTarget.value = false
  scrollToBottomSmooth()
  nextTick(() => {
    textareaRef.value?.focus()
  })
}

const handleRejectPendingApproval = () => {
  if (!pendingApprovalMessage.value) return
  isPendingApprovalMenuOpen.value = false
  isEditingApprovalTarget.value = false
  const msgId = pendingApprovalMessage.value.id
  chatStore.rejectOperation(msgId)
  scrollToBottomSmooth()
  nextTick(() => {
    textareaRef.value?.focus()
  })
}

// 键盘快捷键监听：当存在待确认操作时，Esc 拒绝，Enter 允许
const handleApprovalKeyDown = (e: KeyboardEvent) => {
  if (!pendingApprovalMessage.value) return
  if (isEditingApprovalTarget.value) return // 用户正在就地编辑参数，不拦截按键

  if (e.key === 'Escape') {
    e.preventDefault()
    handleRejectPendingApproval()
  } else if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault()
    handleApprovePendingApproval(false)
  }
}

// 点击页面外部区域关闭下拉弹窗
const handleClickOutside = (e: MouseEvent) => {
  if (modelDropdownRef.value && !modelDropdownRef.value.contains(e.target as Node)) {
    showModelDropdown.value = false
  }
  if (approvalDropdownRef.value && !approvalDropdownRef.value.contains(e.target as Node)) {
    showApprovalDropdown.value = false
  }
  if (exportMenuRef.value && !exportMenuRef.value.contains(e.target as Node)) {
    showExportMenu.value = false
  }
  if (isPendingApprovalMenuOpen.value) {
    isPendingApprovalMenuOpen.value = false
  }
}

onMounted(async () => {
  window.addEventListener('click', handleClickOutside)
  window.addEventListener('keydown', handleApprovalKeyDown)
  window.addEventListener('scroll-chat-to-bottom', handleGlobalScrollToBottom)

  // 组件初次挂载时，无缝恢复当前活跃会话的独立滚动状态
  isSwitchingSession.value = true
  await nextTick()
  if (chatStore.currentSessionId) {
    restoreSessionScroll(chatStore.currentSessionId)
  }
})

onUnmounted(() => {
  window.removeEventListener('click', handleClickOutside)
  window.removeEventListener('keydown', handleApprovalKeyDown)
  window.removeEventListener('scroll-chat-to-bottom', handleGlobalScrollToBottom)
})
</script>

<template>
  <div class="flex-1 flex flex-col h-full bg-gray-50/50 dark:bg-zinc-950 select-none">
    <!-- 顶部状态栏：展示当前会话名称，支持窗口拖拽，移除右侧新建会话按钮 -->
    <header class="h-11 flex items-center justify-between px-5 border-b border-gray-200/80 dark:border-zinc-800/80 bg-white/60 dark:bg-zinc-900/40 backdrop-blur-md z-10 window-drag-region select-none">
      <!-- 左侧：展示当前历史会话标题 -->
      <div class="flex items-center gap-2 min-w-0 max-w-[80%] window-no-drag">
        <span class="text-xs font-semibold text-gray-800 dark:text-zinc-200 truncate">
          {{ currentSessionTitle }}
        </span>
        <span
          v-if="isVirtualScrollActive"
          class="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-800/40 flex items-center gap-1 flex-shrink-0"
          title="已激活动态高度虚拟滚动，视口外超额 DOM 节点自动移出，万条消息不掉帧"
        >
          <Zap class="w-2.5 h-2.5 text-emerald-500" />
          <span>虚拟视口 ({{ displayedMessages.length }}/{{ chatStore.messages.length }})</span>
        </span>
      </div>

      <!-- 右侧：导出对话与清空消息按钮 -->
      <div class="flex items-center gap-1.5 window-no-drag">
        <!-- 多格式会话导出下拉菜单 (Markdown / JSON / Print-PDF) -->
        <div ref="exportMenuRef" class="relative" v-if="chatStore.messages.length > 0">
          <button
            @click.stop="showExportMenu = !showExportMenu"
            class="flex items-center gap-1 px-2.5 py-1 rounded-lg text-gray-500 hover:text-gray-800 dark:text-zinc-400 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 text-xs transition-colors cursor-pointer"
            title="导出当前会话"
          >
            <Download class="w-3.5 h-3.5" />
            <span>导出</span>
            <ChevronDown class="w-3 h-3 transition-transform duration-150" :class="{ 'rotate-180': showExportMenu }" />
          </button>

          <!-- 导出选项气泡卡片 -->
          <transition
            enter-active-class="transition duration-100 ease-out"
            enter-from-class="opacity-0 scale-95 -translate-y-1"
            enter-to-class="opacity-100 scale-100 translate-y-0"
            leave-active-class="transition duration-75 ease-in"
            leave-from-class="opacity-100 scale-100 translate-y-0"
            leave-to-class="opacity-0 scale-95 -translate-y-1"
          >
            <div
              v-if="showExportMenu"
              class="absolute right-0 top-full mt-1.5 w-44 bg-white dark:bg-zinc-900 border border-gray-200/90 dark:border-zinc-800 rounded-xl shadow-xl p-1.5 z-50 select-none text-xs"
              @click.stop
            >
              <button
                @click="exportConversationMarkdown(); showExportMenu = false"
                class="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-gray-700 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors text-left cursor-pointer"
              >
                <FileText class="w-3.5 h-3.5 text-blue-500" />
                <span>Markdown (.md)</span>
              </button>
              <button
                @click="exportConversationJSON"
                class="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-gray-700 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors text-left cursor-pointer"
              >
                <FileCode class="w-3.5 h-3.5 text-emerald-500" />
                <span>结构化 JSON (.json)</span>
              </button>
              <button
                @click="printConversationPDF"
                class="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-gray-700 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors text-left cursor-pointer"
              >
                <Printer class="w-3.5 h-3.5 text-purple-500" />
                <span>打印 / 另存为 PDF</span>
              </button>
            </div>
          </transition>
        </div>

        <button
          v-if="chatStore.messages.length > 0"
          @click="handleClearChat"
          class="flex items-center gap-1 px-2 py-1 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 text-xs transition-colors cursor-pointer"
          title="清空当前会话的消息记录"
        >
          <Trash2 class="w-3.5 h-3.5" />
          <span>清空</span>
        </button>
      </div>
    </header>

    <!-- 消息流滚动展示容器（高度占满，文字可自然划至底部悬浮输入框下方） -->
    <div ref="scrollContainer" @scroll="handleScroll" class="flex-1 overflow-y-auto select-text">
      <!-- 空白引导页 (新对话欢迎界面) -->
      <div v-if="chatStore.messages.length === 0" class="h-full flex flex-col items-center justify-center max-w-xl mx-auto text-center px-4 pt-8 pb-32">
        <img src="/logo.png" alt="NexusDesk Logo" class="w-16 h-16 mb-4 select-none object-contain" />
        <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-2">
          NexusDesk 能为你提供什么帮助？
        </h2>
        <p class="text-xs text-gray-500 dark:text-zinc-400 mb-8 max-w-md">
          支持实时网络搜索、知识库事实检索、数据计算分析与专业内容策划。请在下方输入框直接提问或参考推荐体验：
        </p>

        <!-- 推荐体验场景卡片 -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 w-full text-left">
          <button
            @click="applyPromptSuggestion('帮我分析一组销售业绩数据，并给出前 10 个数据点的趋势与复合增长率分析。')"
            class="p-3 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 hover:border-gray-300 dark:hover:border-zinc-600 transition-all text-xs group"
          >
            <div class="flex items-center gap-2 font-semibold text-gray-800 dark:text-zinc-200 mb-1 group-hover:text-gray-900 dark:group-hover:text-zinc-100">
              <Code2 class="w-4 h-4 text-gray-500 dark:text-zinc-400" />
              <span>数据运算与趋势分析</span>
            </div>
            <div class="text-[11px] text-gray-500 dark:text-zinc-400">利用精准计算与统计能力处理分析数据</div>
          </button>

          <button
            @click="applyPromptSuggestion('检索最近关于人工智能 Agent 的最新前沿突破与核心行业动态，整理成一份简报。')"
            class="p-3 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 hover:border-gray-300 dark:hover:border-zinc-600 transition-all text-xs group"
          >
            <div class="flex items-center gap-2 font-semibold text-gray-800 dark:text-zinc-200 mb-1 group-hover:text-gray-900 dark:group-hover:text-zinc-100">
              <Search class="w-4 h-4 text-gray-500 dark:text-zinc-400" />
              <span>互联网实时深度调研</span>
            </div>
            <div class="text-[11px] text-gray-500 dark:text-zinc-400">联网获取最新公开资讯并总结核心要点</div>
          </button>

          <button
            @click="applyPromptSuggestion('查阅我的知识库文档，告诉我其中关于核心架构与关键指南的说明。')"
            class="p-3 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 hover:border-gray-300 dark:hover:border-zinc-600 transition-all text-xs group"
          >
            <div class="flex items-center gap-2 font-semibold text-gray-800 dark:text-zinc-200 mb-1 group-hover:text-gray-900 dark:group-hover:text-zinc-100">
              <BookOpen class="w-4 h-4 text-gray-500 dark:text-zinc-400" />
              <span>个人知识库精准问答</span>
            </div>
            <div class="text-[11px] text-gray-500 dark:text-zinc-400">深度依托已上传文档提供可靠事实支撑</div>
          </button>

          <button
            @click="applyPromptSuggestion('为一款面向团队效率提升的新产品构思一份引人入胜的发布会演讲大纲。')"
            class="p-3 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 hover:border-gray-300 dark:hover:border-zinc-600 transition-all text-xs group"
          >
            <div class="flex items-center gap-2 font-semibold text-gray-800 dark:text-zinc-200 mb-1 group-hover:text-gray-900 dark:group-hover:text-zinc-100">
              <FileText class="w-4 h-4 text-gray-500 dark:text-zinc-400" />
              <span>创意策划与文案撰写</span>
            </div>
            <div class="text-[11px] text-gray-500 dark:text-zinc-400">发散思维构想，生成专业结构化方案</div>
          </button>
        </div>
      </div>

      <!-- 历史与实时消息列表 (底部预留 pb-36 保证滑至底部时不被输入框遮挡) -->
      <div v-else ref="messagesListRef" class="max-w-4xl mx-auto px-4 pt-4 pb-36 space-y-4 w-full">
        <!-- 虚拟滚动顶部撑高占位 (动态维持滚动条真实高度) -->
        <div v-if="topSpacerHeight > 0" :style="{ height: `${topSpacerHeight}px` }" class="w-full pointer-events-none" />

        <div
          v-for="msg in displayedMessages"
          :key="msg.id"
          :ref="(el) => recordMessageHeight(msg.id, el as HTMLElement)"
          class="message-item-container w-full"
        >
          <ChatMessage :message="msg" />
        </div>

        <!-- 虚拟滚动底部撑高占位 (动态维持滚动条真实高度) -->
        <div v-if="bottomSpacerHeight > 0" :style="{ height: `${bottomSpacerHeight}px` }" class="w-full pointer-events-none" />
      </div>
    </div>

    <!-- 底部输入交互区域（绝对定位纯净悬浮，背景渐变过渡，文字可穿透划入输入框下方） -->
    <div class="absolute bottom-0 left-0 right-0 pointer-events-none pb-5 pt-8 px-4 bg-gradient-to-t from-white via-white/80 to-transparent dark:from-zinc-950 dark:via-zinc-950/80 dark:to-transparent">
      <div class="max-w-4xl mx-auto w-full pointer-events-auto">
        <!-- 悬浮的“回到底部”圆形按钮 (1:1 对标参考截图：纯净圆圈 + 向下箭头 ↓) -->
        <transition
          enter-active-class="transition duration-200 ease-out"
          enter-from-class="opacity-0 translate-y-2 scale-90"
          enter-to-class="opacity-100 translate-y-0 scale-100"
          leave-active-class="transition duration-150 ease-in"
          leave-from-class="opacity-100 translate-y-0 scale-100"
          leave-to-class="opacity-0 translate-y-2 scale-90"
        >
          <div v-if="showScrollBottomBtn" class="flex justify-center mb-3 relative z-30 pointer-events-auto">
            <button
              @click="scrollToBottomSmooth"
              type="button"
              class="w-9 h-9 rounded-full bg-white dark:bg-zinc-800 border border-gray-200/90 dark:border-zinc-700/80 shadow-md hover:shadow-lg text-gray-700 dark:text-zinc-200 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-zinc-750 flex items-center justify-center transition-all hover:scale-105 active:scale-95 cursor-pointer group"
              title="回到底部"
            >
              <ArrowDown class="w-4 h-4 stroke-[1.8] text-gray-700 dark:text-zinc-200 transition-transform group-hover:translate-y-0.5" />
            </button>
          </div>
        </transition>

        <transition
          mode="out-in"
          enter-active-class="transition duration-150 ease-out"
          enter-from-class="opacity-0 scale-[0.98] translate-y-1"
          enter-to-class="opacity-100 scale-100 translate-y-0"
          leave-active-class="transition duration-100 ease-in"
          leave-from-class="opacity-100 scale-100 translate-y-0"
          leave-to-class="opacity-0 scale-[0.98] translate-y-1"
        >
          <!-- 1. 当存在待审批敏感操作时：输入框区域直接化身为人审批确认卡片（1:1 对标参考截图） -->
          <div
            v-if="pendingApprovalMessage"
            key="approval-card"
            class="relative rounded-[24px] border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-xl shadow-gray-200/40 dark:shadow-zinc-950/70 p-5 select-none transition-all"
          >
            <!-- 1. 顶部：工具图标与类别名称 (如 [>_] 终端) -->
            <div class="flex items-center gap-2 text-zinc-500 dark:text-zinc-400 text-xs mb-2.5">
              <SquareTerminal v-if="isPendingTerminalAction" class="w-4 h-4 text-zinc-500 flex-shrink-0" />
              <Trash2 v-else-if="isPendingDeleteAction" class="w-4 h-4 text-zinc-500 flex-shrink-0" />
              <Folder v-else-if="isPendingFolderAction" class="w-4 h-4 text-zinc-500 flex-shrink-0" />
              <SquareTerminal v-else class="w-4 h-4 text-zinc-500 flex-shrink-0" />
              <span>{{ pendingApprovalCategoryName }}</span>
            </div>

            <!-- 2. 标题自然提问 (如: 允许我执行此终端命令吗？ 或 允许我在桌面创建名为“55”的文件夹吗？) -->
            <div class="font-semibold text-[15.5px] text-zinc-900 dark:text-zinc-100 leading-snug tracking-tight mb-2.5">
              {{ pendingApprovalQuestion }}
            </div>

            <!-- 3. 目标命令或路径 (支持人在回路就地编辑修改) -->
            <div v-if="isEditingApprovalTarget" class="mb-4">
              <div class="flex items-center gap-1.5 text-xs text-cyan-600 dark:text-cyan-400 font-medium mb-1.5">
                <Pencil class="w-3.5 h-3.5" />
                <span>人在回路：就地修改执行参数 / 终端命令</span>
              </div>
              <textarea
                v-model="editedApprovalTarget"
                rows="2"
                class="w-full font-mono text-xs p-2.5 rounded-xl border border-cyan-500/80 bg-cyan-50/20 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 outline-none focus:ring-1 focus:ring-cyan-500 transition-all select-text"
                placeholder="在此修改待执行的指令或路径参数..."
              ></textarea>
            </div>
            <div
              v-else-if="pendingApprovalMessage.approvalData?.target"
              class="font-mono text-xs text-zinc-400 dark:text-zinc-500 select-all mb-4 break-all leading-normal"
            >
              {{ pendingApprovalMessage.approvalData.target }}
            </div>

            <!-- 4. 底部操作区 (完美还原参考图细节：拒绝 Esc 与 允许一次 ↵ | v) -->
            <div class="flex items-center justify-end gap-2.5 relative">
              <!-- 修改参数按钮 (人在回路 HITL 参数调整) -->
              <button
                @click="toggleEditApprovalTarget"
                type="button"
                class="h-8 px-3 rounded-full border border-gray-200/90 dark:border-zinc-700 bg-white hover:bg-gray-100 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-300 text-xs font-medium transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs"
                :title="isEditingApprovalTarget ? '取消编辑参数' : '人在回路：先修改指令参数再批准执行'"
              >
                <Pencil class="w-3 h-3 text-zinc-500" />
                <span>{{ isEditingApprovalTarget ? '取消编辑' : '修改参数' }}</span>
              </button>

              <!-- 拒绝按钮 (支持 Esc 快捷键) -->
              <button
                @click="handleRejectPendingApproval"
                type="button"
                class="h-8 px-3.5 rounded-full border border-gray-200/90 dark:border-zinc-700 bg-white hover:bg-gray-100 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-zinc-800 dark:text-zinc-200 text-xs font-medium transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs"
                title="按 Esc 键拒绝"
              >
                <span>拒绝</span>
                <span class="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-zinc-700 text-[10px] font-sans text-gray-500 dark:text-zinc-400 font-normal leading-none">Esc</span>
              </button>

              <!-- 允许一次 / 允许类似命令 组合按钮 -->
              <div class="relative inline-flex items-center rounded-full bg-[#18181b] dark:bg-zinc-100 text-white dark:text-zinc-900 shadow-sm overflow-visible">
                <!-- 允许一次 主按钮 (带有 1.5px 蓝色边框完全环绕左侧药丸) -->
                <button
                  @click="handleApprovePendingApproval(false)"
                  type="button"
                  class="h-8 flex items-center gap-1.5 pl-3.5 pr-2.5 rounded-l-full border-2 border-[#1677ff] bg-[#18181b] hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-white text-white dark:text-zinc-900 text-xs font-medium transition-colors cursor-pointer"
                  title="按 Enter 键允许"
                >
                  <span>允许一次</span>
                  <span class="rounded bg-[#2a2a2e] dark:bg-zinc-300 px-1 py-0.5 flex items-center justify-center">
                    <CornerDownLeft class="w-3 h-3 text-white dark:text-zinc-900 stroke-[2.2]" />
                  </span>
                </button>

                <!-- 下拉展开按钮 -->
                <button
                  @click.stop="isPendingApprovalMenuOpen = !isPendingApprovalMenuOpen"
                  type="button"
                  class="h-8 px-2 rounded-r-full bg-[#27272a] hover:bg-[#3f3f46] dark:bg-zinc-200 dark:hover:bg-zinc-300 text-white dark:text-zinc-900 transition-colors flex items-center justify-center cursor-pointer"
                  title="更多授权选项"
                >
                  <ChevronDown class="w-3.5 h-3.5 stroke-[2] transition-transform duration-150" :class="{ 'rotate-180': isPendingApprovalMenuOpen }" />
                </button>

                <!-- 悬浮弹窗 (对标图 2 样式) -->
                <transition
                  enter-active-class="transition duration-150 ease-out"
                  enter-from-class="opacity-0 translate-y-1 scale-95"
                  enter-to-class="opacity-100 translate-y-0 scale-100"
                  leave-active-class="transition duration-100 ease-in"
                  leave-from-class="opacity-100 translate-y-0 scale-100"
                  leave-to-class="opacity-0 translate-y-1 scale-95"
                >
                  <div
                    v-if="isPendingApprovalMenuOpen"
                    class="absolute bottom-full right-0 mb-2 w-44 bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded-2xl shadow-xl p-1.5 z-50 select-none"
                    @click.stop
                  >
                    <button
                      @click="handleApprovePendingApproval(false)"
                      type="button"
                      class="w-full text-left px-3 py-2 text-xs text-gray-800 dark:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-700 rounded-xl transition-colors cursor-pointer"
                    >
                      允许一次
                    </button>
                    <button
                      @click="handleApprovePendingApproval(true)"
                      type="button"
                      class="flex items-center justify-between w-full px-3 py-2 text-xs text-gray-800 dark:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-700 rounded-xl transition-colors cursor-pointer group"
                      title="在当前会话中对类似命令默认允许"
                    >
                      <span>允许类似命令</span>
                      <Info class="w-3.5 h-3.5 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-zinc-300" />
                    </button>
                  </div>
                </transition>
              </div>
            </div>
          </div>

          <!-- 2. 常规状态：展示多模态提问输入框 -->
          <div
            v-else
            key="chat-input"
            @dragover="handleDragOver"
            @dragleave="handleDragLeave"
            @drop="handleDrop"
            class="relative rounded-[24px] border border-gray-200/90 dark:border-zinc-800 bg-white/95 dark:bg-zinc-900/95 backdrop-blur-md shadow-xl shadow-gray-200/40 dark:shadow-zinc-950/70 focus-within:border-gray-300 dark:focus-within:border-zinc-600 focus-within:ring-2 focus-within:ring-gray-400/10 transition-all"
            :class="{ 'border-gray-400 ring-2 ring-gray-400/25 bg-gray-100/40 dark:bg-zinc-800/40': isDraggingOver }"
          >
          <!-- 拖拽图片或文档悬停视觉引导遮罩 -->
          <div
            v-if="isDraggingOver"
            class="absolute inset-0 rounded-[24px] bg-gray-400/15 backdrop-blur-xs flex items-center justify-center pointer-events-none z-30 text-gray-600 dark:text-zinc-300 text-xs font-medium"
          >
            释放图片或文件即可添加到对话
          </div>

          <!-- 待发送的多模态图片与文档附件缩略图预览条目 -->
          <div
            v-if="attachedImages.length > 0 || attachedDocs.length > 0"
            class="px-4 pt-3 pb-1 flex flex-wrap gap-2.5 items-center select-none"
          >
            <!-- 1. 图片缩略图 -->
            <div
              v-for="(img, idx) in attachedImages"
              :key="'img_' + idx"
              class="relative w-14 h-14 rounded-xl border border-gray-200 dark:border-zinc-700 overflow-hidden shadow-xs group/thumb bg-gray-50 dark:bg-zinc-800 flex-shrink-0"
            >
              <img :src="img" class="w-full h-full object-cover" />
              <!-- 删除缩略图按钮 -->
              <button
                @click="removeAttachedImage(idx)"
                type="button"
                class="absolute top-1 right-1 w-4 h-4 rounded-full bg-black/65 hover:bg-black/90 text-white flex items-center justify-center transition-colors cursor-pointer"
                title="移除此图片"
              >
                <XIcon class="w-2.5 h-2.5" />
              </button>
            </div>

            <!-- 2. 文档与代码附件卡片（支持 PDF 与代码文件，带解析中状态指示） -->
            <div
              v-for="(doc, idx) in attachedDocs"
              :key="doc.id"
              class="flex items-center gap-2 px-2.5 py-1.5 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-xs shadow-2xs select-none flex-shrink-0 group/doc"
            >
              <Loader2 v-if="doc.loading" class="w-4 h-4 text-gray-500 dark:text-zinc-400 animate-spin flex-shrink-0" />
              <span v-else-if="doc.isPdf" class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-600 dark:bg-zinc-500 text-white leading-none">PDF</span>
              <FileCode v-else class="w-4 h-4 text-gray-500 dark:text-zinc-400 flex-shrink-0" />

              <div class="flex flex-col min-w-0 max-w-[140px]">
                <span class="truncate font-medium text-gray-800 dark:text-zinc-200 text-[11px] leading-tight" :title="doc.name">{{ doc.name }}</span>
                <span class="text-[10px] text-gray-400 leading-tight">
                  <template v-if="doc.loading">解析中...</template>
                  <template v-else>
                    {{ formatFileSize(doc.size) }}<template v-if="doc.pages"> · {{ doc.pages }}页</template>
                  </template>
                </span>
              </div>
              <button
                @click="removeAttachedDoc(idx)"
                type="button"
                class="p-0.5 rounded-full hover:bg-gray-200 dark:hover:bg-zinc-700 text-gray-400 hover:text-gray-700 dark:hover:text-zinc-200 transition-colors cursor-pointer"
                title="移除文件"
              >
                <XIcon class="w-3 h-3" />
              </button>
            </div>
          </div>

          <!-- Textarea 提问输入区 (支持长文本与代码粘贴高度平滑自适应) -->
          <textarea
            ref="textareaRef"
            v-model="inputText"
            @input="adjustTextareaHeight"
            @keydown="handleKeyDown"
            @paste="handlePaste"
            @compositionstart="handleCompositionStart"
            @compositionend="handleCompositionEnd"
            placeholder="随心输入，按上下键切换历史，支持粘贴/拖入图片与PDF文档..."
            class="w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-[13.5px] text-gray-900 dark:text-zinc-100 placeholder-gray-400 dark:placeholder-zinc-500 focus:outline-none leading-relaxed transition-[height] duration-75"
            style="min-height: 44px; max-height: 180px; box-sizing: border-box;"
          ></textarea>

          <!-- 底部快捷工具条 -->
          <div class="flex items-center justify-between px-3 pb-2.5 pt-0.5 select-none">
            
            <!-- 左侧：新建 + 上传图片 + 权限模式状态徽标 -->
            <div class="flex items-center gap-1.5">
              <!-- 隐藏的本地图片/文档选择 input -->
              <input
                ref="fileInputRef"
                type="file"
                accept="image/*,.pdf,application/pdf,.txt,.md,.markdown,.json,.csv,.tsv,.xml,.yaml,.yml,.py,.js,.ts,.jsx,.tsx,.html,.css,.scss,.vue,.sh,.sql,.log,.env,.toml"
                multiple
                class="hidden"
                @change="handleFileSelect"
              />

              <!-- 加号按钮：直接打开文件/图片选择 -->
              <button
                type="button"
                @click="triggerFileInput"
                class="p-1 text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-100 rounded-full hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
                title="添加图片或文件 (支持粘贴与拖拽)"
              >
                <Plus class="w-4 h-4" />
              </button>

              <!-- 权限模式快捷切换触发器与弹出菜单 (对标参考图) -->
              <div ref="approvalDropdownRef" class="relative">
                <!-- 帮我批准 (默认) -->
                <button
                  v-if="settingsStore.approvalMode === 'smart'"
                  @click.stop="showApprovalDropdown = !showApprovalDropdown"
                  type="button"
                  class="flex items-center gap-1 px-1.5 py-0.5 rounded-md text-xs font-medium text-gray-700 dark:text-zinc-300 hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors cursor-pointer"
                  title="点击配置操作批准模式"
                >
                  <ShieldCheck class="w-3.5 h-3.5 text-gray-600 dark:text-zinc-400 flex-shrink-0" />
                  <span>帮我批准</span>
                </button>

                <!-- 请求批准 -->
                <button
                  v-else-if="settingsStore.approvalMode === 'ask_always'"
                  @click.stop="showApprovalDropdown = !showApprovalDropdown"
                  type="button"
                  class="flex items-center gap-1 px-1.5 py-0.5 rounded-md text-xs font-medium text-gray-700 dark:text-zinc-300 hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors cursor-pointer"
                  title="点击配置操作批准模式"
                >
                  <Hand class="w-3.5 h-3.5 text-gray-600 dark:text-zinc-400 flex-shrink-0" />
                  <span>请求批准</span>
                </button>

                <!-- 完全访问 -->
                <button
                  v-else
                  @click.stop="showApprovalDropdown = !showApprovalDropdown"
                  type="button"
                  class="flex items-center gap-1 px-1.5 py-0.5 rounded-md text-xs font-medium text-[#E56018] dark:text-orange-400 hover:bg-orange-50/60 dark:hover:bg-orange-950/20 transition-colors cursor-pointer"
                  title="点击配置操作批准模式"
                >
                  <AlertTriangle class="w-3.5 h-3.5 flex-shrink-0" />
                  <span>完全访问</span>
                </button>

                <!-- 批准模式 Popover 下拉菜单（1:1 对标参考截图） -->
                <div
                  v-if="showApprovalDropdown"
                  class="absolute bottom-full mb-2 left-0 w-80 sm:w-88 rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xl p-2 z-50 select-none space-y-1"
                >
                  <!-- 顶栏标题与说明 -->
                  <div class="px-3 pt-1.5 pb-2 flex items-center justify-between text-xs text-gray-500 dark:text-zinc-400 border-b border-gray-100 dark:border-zinc-800/80">
                    <span class="font-medium text-gray-700 dark:text-zinc-300">应如何批准智能体操作？</span>
                    <router-link to="/settings" class="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300 hover:underline">了解更多</router-link>
                  </div>

                  <!-- 模式 1: 请求批准 -->
                  <div
                    @click="selectApprovalMode('ask_always')"
                    class="p-2.5 rounded-xl flex items-start justify-between gap-3 cursor-pointer transition-colors"
                    :class="[settingsStore.approvalMode === 'ask_always' ? 'bg-black/[0.05] dark:bg-white/[0.08]' : 'hover:bg-black/[0.03] dark:hover:bg-white/[0.05]']"
                  >
                    <div class="flex items-start gap-2.5 min-w-0">
                      <Hand class="w-4 h-4 mt-0.5 text-gray-700 dark:text-zinc-300 flex-shrink-0" />
                      <div>
                        <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100 leading-tight">请求批准</div>
                        <div class="text-[11px] text-gray-500 dark:text-zinc-400 mt-0.5 leading-snug">编辑外部文件和使用互联网时始终询问</div>
                      </div>
                    </div>
                    <Check v-if="settingsStore.approvalMode === 'ask_always'" class="w-4 h-4 text-gray-900 dark:text-white flex-shrink-0 mt-0.5" />
                  </div>

                  <!-- 模式 2: 帮我批准 (默认推荐) -->
                  <div
                    @click="selectApprovalMode('smart')"
                    class="p-2.5 rounded-xl flex items-start justify-between gap-3 cursor-pointer transition-colors"
                    :class="[settingsStore.approvalMode === 'smart' ? 'bg-black/[0.05] dark:bg-white/[0.08]' : 'hover:bg-black/[0.03] dark:hover:bg-white/[0.05]']"
                  >
                    <div class="flex items-start gap-2.5 min-w-0">
                      <ShieldCheck class="w-4 h-4 mt-0.5 text-gray-700 dark:text-zinc-300 flex-shrink-0" />
                      <div>
                        <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100 leading-tight">帮我批准</div>
                        <div class="text-[11px] text-gray-500 dark:text-zinc-400 mt-0.5 leading-snug">仅对检测到的风险操作请求批准</div>
                      </div>
                    </div>
                    <Check v-if="settingsStore.approvalMode === 'smart'" class="w-4 h-4 text-gray-900 dark:text-white flex-shrink-0 mt-0.5" />
                  </div>

                  <!-- 模式 3: 完全访问权限 -->
                  <div
                    @click="selectApprovalMode('full_access')"
                    class="p-2.5 rounded-xl flex items-start justify-between gap-3 cursor-pointer transition-colors"
                    :class="[settingsStore.approvalMode === 'full_access' ? 'bg-amber-500/[0.08] dark:bg-amber-500/[0.12]' : 'hover:bg-black/[0.03] dark:hover:bg-white/[0.05]']"
                  >
                    <div class="flex items-start gap-2.5 min-w-0">
                      <AlertTriangle class="w-4 h-4 mt-0.5 text-[#E06714] dark:text-[#F97316] flex-shrink-0" />
                      <div>
                        <div class="text-[13px] font-semibold text-[#E06714] dark:text-[#F97316] leading-tight">完全访问权限</div>
                        <div class="text-[11px] text-[#E06714]/85 dark:text-[#F97316]/85 mt-0.5 leading-snug">可不受限制地访问互联网和你电脑上的任何文件</div>
                      </div>
                    </div>
                    <Check v-if="settingsStore.approvalMode === 'full_access'" class="w-4 h-4 text-[#E06714] dark:text-[#F97316] flex-shrink-0 mt-0.5" />
                  </div>
                </div>
              </div>
            </div>

            <!-- 右侧：模型切换 + 麦克风 + 蓝色圆形发送按钮 -->
            <div class="flex items-center gap-2">
              
              <!-- 当前模型指示与快捷下拉切换器 -->
              <div ref="modelDropdownRef" class="relative">
                <button
                  @click.stop="showModelDropdown = !showModelDropdown"
                  type="button"
                  class="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-gray-600 dark:text-zinc-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
                  title="点击快速切换模型或查看配置"
                >
                  <span class="max-w-[140px] truncate">{{ settingsStore.model }}</span>
                  <ChevronDown class="w-3 h-3 text-gray-400 transition-transform" :class="{ 'rotate-180': showModelDropdown }" />
                </button>

                <!-- 模型快捷下拉面板（浮动于输入框上方） -->
                <div
                  v-if="showModelDropdown"
                  class="absolute right-0 bottom-full mb-2 w-64 p-2 rounded-xl bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 shadow-xl z-50 text-xs space-y-1.5 animate-in fade-in slide-in-from-bottom-2 duration-150"
                >
                  <div class="px-2 py-1 text-[11px] font-semibold text-gray-400 flex items-center justify-between border-b border-gray-100 dark:border-zinc-800">
                    <span>当前服务商: {{ settingsStore.currentProvider.name }}</span>
                  </div>

                  <!-- 已拉取/可用模型列表 -->
                  <div class="max-h-48 overflow-y-auto space-y-0.5">
                    <button
                      v-for="m in availableQuickModels"
                      :key="m.id"
                      @click="selectQuickModel(m.id)"
                      type="button"
                      class="w-full px-2.5 py-1.5 rounded-lg text-left flex items-center justify-between text-xs transition-colors"
                      :class="[
                        settingsStore.model === m.id
                          ? 'bg-gray-100 dark:bg-zinc-800 text-gray-900 dark:text-zinc-100 font-semibold'
                          : 'hover:bg-gray-100 dark:hover:bg-zinc-800 text-gray-700 dark:text-zinc-300'
                      ]"
                    >
                      <span class="font-mono truncate">{{ m.id }}</span>
                      <Check v-if="settingsStore.model === m.id" class="w-3.5 h-3.5 text-gray-700 dark:text-zinc-200 flex-shrink-0" />
                    </button>
                  </div>

                  <!-- 底部跳转设置入口 -->
                  <div class="pt-1.5 border-t border-gray-100 dark:border-zinc-800">
                    <router-link
                      to="/settings"
                      @click="showModelDropdown = false"
                      class="flex items-center gap-1.5 px-2 py-1 rounded-md text-gray-600 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-800 text-[11px] font-medium transition-colors"
                    >
                      <Sliders class="w-3.5 h-3.5" />
                      <span>模型设置与 API Key 管理 ↗</span>
                    </router-link>
                  </div>
                </div>
              </div>


              <!-- 停止生成按钮 -->
              <button
                v-if="chatStore.isGenerating"
                @click="chatStore.stopGeneration"
                type="button"
                class="w-7 h-7 rounded-full bg-rose-500 hover:bg-rose-600 text-white flex items-center justify-center transition-transform active:scale-95 shadow-xs"
                title="停止生成"
              >
                <Square class="w-3 h-3 fill-current" />
              </button>

              <!-- 发送按钮：浅蓝圆形箭头 (完全对齐截图) -->
              <button
                v-else
                @click="handleSend"
                :disabled="(!inputText.trim() && attachedImages.length === 0 && attachedDocs.length === 0) || attachedDocs.some(d => d.loading)"
                type="button"
                class="w-7 h-7 rounded-full flex items-center justify-center text-white transition-all active:scale-95 shadow-xs disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                :class="[
                  (inputText.trim() || attachedImages.length > 0 || attachedDocs.length > 0) && !attachedDocs.some(d => d.loading)
                    ? 'bg-gray-800 hover:bg-gray-700 dark:bg-zinc-600 dark:hover:bg-zinc-500'
                    : 'bg-gray-300 dark:bg-zinc-700'
                ]"
                title="发送 (Enter)"
              >
                <Loader2 v-if="attachedDocs.some(d => d.loading)" class="w-3.5 h-3.5 animate-spin" />
                <ArrowUp v-else class="w-4 h-4 stroke-[2.5]" />
              </button>
            </div>

          </div>

        </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 虚拟渲染与长列表性能优化：大幅降低数百条长消息滚动渲染压力 */
.message-item-container {
  content-visibility: auto;
  contain-intrinsic-size: 1px 120px;
}

/* 打印与原生另存为 PDF 专属精美排版优化 */
@media print {
  header,
  aside,
  nav,
  .window-drag-region,
  .window-no-drag,
  .pointer-events-none,
  .pointer-events-auto,
  button {
    display: none !important;
  }

  body, html, #app, main, .select-text {
    background: #ffffff !important;
    color: #111827 !important;
    overflow: visible !important;
    height: auto !important;
    padding: 0 !important;
    margin: 0 !important;
  }

  .markdown-body {
    font-size: 12pt !important;
    line-height: 1.6 !important;
  }
}
</style>
