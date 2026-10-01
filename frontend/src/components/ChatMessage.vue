<script setup lang="ts">
/**
 * 对话单条消息展示组件
 * 支持 Markdown 富文本解析与代码高亮渲染、思考链 (CoT) 折叠、工具调用可视化卡片以及一键复制。
 */
import { computed, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import {
  Copy,
  Check,
  AlertCircle,
  FileText,
  RotateCcw,
  Zap,
  Brain,
  ListTodo,
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
  Bot,
} from 'lucide-vue-next'
import ThinkingProcess from './ThinkingProcess.vue'
import type { ChatMessage } from '../stores/chat'
import { useChatStore } from '../stores/chat'
import { cleanApprovalContent } from '../utils/approval'

const getAgentBadgeText = (assigned: NonNullable<ChatMessage['assignedAgent']>): string => {
  const agentMap: Record<string, { label: string; icon: string }> = {
    coder: { label: '代码工程专家', icon: '💻' },
    researcher: { label: '网络调研专家', icon: '📊' },
    terminal: { label: '终端运维专家', icon: '🖥️' },
    rag: { label: '知识库专家', icon: '📚' },
    chat: { label: '极速对话助手', icon: '💬' },
  }
  const meta = agentMap[assigned.agent] || { label: assigned.agent, icon: '🤖' }
  const confText = assigned.confidence ? ` ${(assigned.confidence * 100).toFixed(0)}%` : ''
  return `${meta.icon} ${meta.label}${confText}`
}

const getAgentTooltip = (assigned: NonNullable<ChatMessage['assignedAgent']>): string => {
  const parts: string[] = []
  if (assigned.intent) parts.push(`识别意图: ${assigned.intent}`)
  if (assigned.confidence) parts.push(`置信度: ${(assigned.confidence * 100).toFixed(1)}%`)
  if (assigned.reason) parts.push(`分派理由: ${assigned.reason}`)
  return parts.join(' | ') || 'Laya 意图识别与专家智能体分派'
}

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const props = defineProps<{
  /** 消息体对象 */
  message: ChatMessage
}>()

const chatStore = useChatStore()

// 复制成功的临时状态控制
const isCopied = ref(false)

// 是否存在思考过程或工具调用记录（或处于思考流式中）
const hasThinkingOrTools = computed(() => {
  const cleanThought = (props.message.thought || '')
    .replace(/🎯[\s\S]*?🛡️[^\n]*(?:\n+|$)/g, '')
    .trim()
  return Boolean(
    cleanThought.length > 0 ||
    (props.message.tools && props.message.tools.length > 0) ||
    (props.message.thoughtDuration && props.message.thoughtDuration > 0 && cleanThought.length > 0) ||
    (props.message.isStreaming && !props.message.content)
  )
})

// 初始化 markdown-it 实例
const md: InstanceType<typeof MarkdownIt> = new MarkdownIt({
  html: true,
  linkify: true,
  breaks: true,
})

// 自定义代码块 (fence & code_block) 渲染规则，彻底解决 markdown-it 默认外部包裹 pre/code 导致的黑白多层嵌套显示异常
const renderCustomCodeBlock = (str: string, lang: string = ''): string => {
  const validLang = lang && hljs.getLanguage(lang) ? lang : ''
  let highlighted = ''
  if (validLang) {
    try {
      highlighted = hljs.highlight(str, { language: validLang, ignoreIllegals: true }).value
    } catch (__) {
      highlighted = md.utils.escapeHtml(str)
    }
  } else {
    highlighted = md.utils.escapeHtml(str)
  }

  const langLabel = (validLang || lang || 'code').toLowerCase()
  const encoded = encodeURIComponent(str)

  return `<div class="code-block-container my-3 rounded-xl border border-zinc-800 bg-[#18181b] overflow-hidden text-xs shadow-2xs">
  <div class="code-block-header flex items-center justify-between px-3.5 py-1.5 border-b border-zinc-800/80 bg-[#202024] select-none text-zinc-400">
    <span class="font-mono text-[11px] font-semibold text-zinc-400">${langLabel}</span>
    <button type="button" class="copy-code-btn flex items-center gap-1.5 text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer" data-code="${encoded}" title="复制代码">
      <svg class="w-3.5 h-3.5 icon-copy" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
      <span class="copy-text">复制</span>
    </button>
  </div>
  <pre class="hljs p-3.5 overflow-x-auto font-mono text-[12px] leading-relaxed text-zinc-100 m-0 border-0 bg-transparent rounded-none"><code>${highlighted}</code></pre>
</div>\n`
}

md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const info = token.info ? token.info.trim() : ''
  const lang = info ? info.split(/\s+/g)[0] : ''
  return renderCustomCodeBlock(token.content, lang)
}

md.renderer.rules.code_block = (tokens, idx) => {
  const token = tokens[idx]
  return renderCustomCodeBlock(token.content, '')
}

// 计算解析后的 HTML 富文本（自动净化内部隐藏的 approval json 块，并过滤开头机械复述用户提问的冗余行）
const renderedMarkdown = computed(() => {
  if (!props.message.content) return ''
  let cleaned = cleanApprovalContent(props.message.content)

  // 杜绝 AI 在开头机械复述用户的提问或指令
  if (props.message.role === 'assistant') {
    const idx = chatStore.messages.findIndex(m => m.id === props.message.id)
    if (idx > 0) {
      for (let i = idx - 1; i >= 0; i--) {
        const prev = chatStore.messages[i]
        if (prev.role === 'user') {
          // 提取用户实际输入的提问文本
          let userQuery = prev.content || ''
          userQuery = userQuery.replace(/【用户(?:提问与指令|上传[\s\S]*?)】/g, '')
          userQuery = userQuery.replace(/【[\s\S]*?】/g, '')
          userQuery = userQuery.replace(/```[\s\S]*?```/g, '')
          userQuery = userQuery.trim()

          if (userQuery && userQuery.length <= 40) {
            const escaped = userQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
            // 匹配开头独立行复读，如 "分析一下\n"、"# 分析一下\n"、"好的，分析一下：\n"
            const echoRegex = new RegExp(`^(?:#{1,6}\\s*)?(?:(?:好的|好的，|好的,|收到)[，,]?(?:我来|为您|马上)?)?${escaped}[：:!！。]?\\s*([\\r\\n]+|$)`, 'i')
            if (echoRegex.test(cleaned)) {
              cleaned = cleaned.replace(echoRegex, '').trimStart()
            }
          }
          break
        }
      }
    }
  }
  // 彻底过滤开头多余的“好的，已确认执行”、“已确认”等无意义客套废话
  cleaned = cleaned.replace(/^(?:#{1,6}\s*)?(?:好的[，,！!]?)?\s*(?:已确认|确认执行|好的|收到)[，,！!。\s]*/i, '')

  return md.render(cleaned)
})

// 提取用户消息中关联的文档（优先读取元数据，兜底从历史文本中解析）
const displayDocs = computed(() => {
  if (props.message.docs && props.message.docs.length > 0) {
    return props.message.docs
  }
  const content = props.message.content || ''
  if (!content) return []

  const docs: Array<{ name: string; isPdf?: boolean }> = []
  // 匹配形如 【用户上传附件文档: filename.ext (...)】 或 【用户上传PDF文档(N页): filename.pdf (...)】
  const docRegex = /【用户上传(?:附件文档|PDF文档(?:\(\d+页\))?|文档\/代码):\s*([^\s()]+)(?:\s*\(([^)]*)\))?】/g
  let match
  while ((match = docRegex.exec(content)) !== null) {
    const filename = match[1]
    const isPdf = filename.toLowerCase().endsWith('.pdf') || match[0].includes('PDF文档')
    docs.push({
      name: filename,
      isPdf,
    })
  }
  return docs
})

// 纯化用户提问文本：严格剔除混入其中的文件正文与系统拼接模板，防止聊天气泡被大段文件内容撑爆
const cleanedUserText = computed(() => {
  let text = props.message.content || ''
  if (!text) return ''

  // 1. 彻底剔除形如 【用户上传...】```...``` 的全部附件正文块
  text = text.replace(/【用户(?:上传|参考)[\s\S]*?```[\s\S]*?```/g, '')

  // 2. 彻底剔除模板标题如 【用户提问与指令】、【用户上传参考文档】（...）
  text = text.replace(/【用户提问与指令】\s*/g, '')
  text = text.replace(/【用户上传参考文档】[\s\S]*?：\s*/g, '')

  // 3. 彻底剔除未闭合或单行的 【用户上传...】 标记
  text = text.replace(/【用户上传[^】]+】/g, '')

  // 4. 剔除默认的前置引导句
  text = text.replace(/请查阅并(?:分析|处理)我上传的(?:附件)?文档：?/g, '')

  return text.trim()
})

const formatTime = (ts?: number) => {
  if (!ts) return ''
  const d = new Date(ts)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

// 复制消息正文到剪贴板
const copyText = async (textToCopy?: string | any) => {
  try {
    const text = typeof textToCopy === 'string' ? textToCopy : props.message.content
    if (!text) return
    await navigator.clipboard.writeText(text)
    isCopied.value = true
    setTimeout(() => {
      isCopied.value = false
    }, 2000)
  } catch (err) {
    console.error('复制内容失败', err)
  }
}

// 点击大图预览
const activePreviewImage = ref<string | null>(null)
const previewImage = (url: string) => {
  activePreviewImage.value = url
}



// 重新生成此条回答
const handleRegenerate = () => {
  chatStore.regenerateMessage(props.message.id)
}

// 代理 markdown 代码块顶部复制按钮的点击事件
const handleMarkdownClick = async (e: MouseEvent) => {
  const btn = (e.target as HTMLElement).closest('.copy-code-btn') as HTMLElement | null
  if (!btn) return
  e.stopPropagation()

  const rawCode = btn.getAttribute('data-code')
  if (!rawCode) return

  const code = decodeURIComponent(rawCode)
  try {
    await navigator.clipboard.writeText(code)
    const textSpan = btn.querySelector('.copy-text')
    if (textSpan) textSpan.textContent = '已复制'
    btn.classList.add('text-emerald-600', 'dark:text-emerald-400')
    setTimeout(() => {
      if (textSpan) textSpan.textContent = '复制'
      btn.classList.remove('text-emerald-600', 'dark:text-emerald-400')
    }, 2000)
  } catch (err) {
    console.error('复制代码失败', err)
  }
}
</script>

<template>
  <div class="w-full">
    <!-- 用户提问区域：右对齐，包含上方独立文件胶囊与下方气泡，完全对齐截图样式 -->
    <div v-if="message.role === 'user'" class="flex flex-col items-end w-full my-3">
      <!-- 1. 上传的文件胶囊列表（位于气泡上方独立展示，对标用户截图） -->
      <div v-if="displayDocs.length > 0" class="flex flex-col items-end gap-1.5 mb-1.5">
        <div
          v-for="(doc, idx) in displayDocs"
          :key="idx"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-gray-200/90 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-gray-800 dark:text-zinc-200 shadow-2xs select-none max-w-full"
        >
          <span v-if="doc.isPdf" class="px-1 py-0.5 rounded text-[9px] font-bold bg-gray-600 dark:bg-zinc-500 text-white leading-none">PDF</span>
          <FileText v-else class="w-3.5 h-3.5 text-gray-500 dark:text-zinc-400 flex-shrink-0 stroke-[1.8]" />
          <span class="truncate text-xs font-normal" :title="doc.name">{{ doc.name }}</span>
        </div>
      </div>

      <!-- 2. 用户上传图片预览 (如有) -->
      <div v-if="message.images && message.images.length > 0" class="flex flex-wrap justify-end gap-2 mb-1.5">
        <div
          v-for="(img, idx) in message.images"
          :key="idx"
          class="relative rounded-xl overflow-hidden border border-gray-200 dark:border-zinc-700 shadow-xs cursor-pointer group/img"
          @click="previewImage(img)"
          title="点击查看大图"
        >
          <img
            :src="img"
            alt="用户上传图片"
            class="max-w-[240px] max-h-[180px] object-cover hover:scale-105 transition-transform duration-200"
          />
        </div>
      </div>

      <!-- 3. 用户提问气泡（仅在有实际输入文本时展示，完全对齐截图样式） -->
      <div
        v-if="cleanedUserText"
        class="group relative max-w-[85%] sm:max-w-[78%] px-4 py-2 sm:px-5 sm:py-2.5 rounded-[18px] bg-gray-100 dark:bg-zinc-800 text-gray-900 dark:text-zinc-100 text-[13.5px] leading-relaxed shadow-xs border border-gray-200 dark:border-zinc-700 break-words whitespace-pre-wrap select-text"
      >
        <span>{{ cleanedUserText }}</span>

        <!-- 悬停快捷复制按钮 -->
        <button
          @click="copyText(cleanedUserText)"
          class="absolute -left-7 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 text-gray-400 hover:text-gray-600 dark:hover:text-zinc-200 transition-opacity p-1 rounded cursor-pointer"
          title="复制提问"
        >
          <Check v-if="isCopied" class="w-3.5 h-3.5 text-gray-500 dark:text-zinc-400" />
          <Copy v-else class="w-3.5 h-3.5" />
        </button>
      </div>

      <!-- 4. 底部微型时间与复制工具栏（对标截图中的 15:26 和图标） -->
      <div class="flex items-center gap-1.5 mt-1 text-[11px] text-gray-400 dark:text-zinc-500 select-none pr-1">
        <span v-if="message.timestamp">{{ formatTime(message.timestamp) }}</span>
        <button
          @click="copyText(cleanedUserText || (displayDocs[0]?.name || ''))"
          class="p-0.5 hover:text-gray-600 dark:hover:text-zinc-300 transition-colors cursor-pointer"
          title="复制内容"
        >
          <Check v-if="isCopied" class="w-3 h-3 text-gray-500 dark:text-zinc-400" />
          <Copy v-else class="w-3 h-3" />
        </button>
      </div>
    </div>

    <!-- 助手回复区域：左对齐纯净自然文本流，仅在角色为 assistant 或 system 时渲染 -->
    <div v-else-if="message.role === 'assistant' || message.role === 'system'" class="group w-full my-3 text-[13.5px] text-gray-800 dark:text-zinc-200">
      <!-- 0. 智能模型动态路由与多智能体分派指示胶囊 -->
      <div v-if="message.routedModel || message.assignedAgent" class="flex flex-wrap items-center gap-2 mb-2">
        <div v-if="message.routedModel" class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-cyan-50/80 dark:bg-cyan-950/40 text-cyan-700 dark:text-cyan-300 border border-cyan-200/70 dark:border-cyan-800/50" :title="message.routedModel.reason || ''">
          <Zap v-if="message.routedModel.tier === 'fast'" class="w-3 h-3 text-cyan-500" />
          <Brain v-else class="w-3 h-3 text-indigo-500" />
          <span>{{ message.routedModel.tier === 'fast' ? '⚡ 极速模型' : '🧠 深度推理' }} ({{ message.routedModel.model }})</span>
        </div>
        <div v-if="message.assignedAgent" class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-purple-50/80 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border border-purple-200/70 dark:border-purple-800/50" :title="getAgentTooltip(message.assignedAgent)">
          <Bot class="w-3 h-3 text-purple-500" />
          <span>{{ getAgentBadgeText(message.assignedAgent) }}</span>
        </div>
      </div>

      <!-- 0.5 长程任务规划与执行阶段清单 (Plan-and-Solve) -->
      <div v-if="message.plan && message.plan.length > 0" class="mb-3 p-3.5 rounded-2xl bg-white/70 dark:bg-zinc-900/60 border border-gray-200/80 dark:border-zinc-800 shadow-2xs">
        <div class="flex items-center justify-between text-xs font-semibold text-gray-800 dark:text-zinc-200 mb-2">
          <span class="flex items-center gap-1.5">
            <ListTodo class="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
            <span>长程任务规划状态机 (Plan-and-Solve)</span>
          </span>
          <span class="text-[10px] text-gray-400 font-normal">共 {{ message.plan.length }} 个阶段</span>
        </div>
        <div class="space-y-1.5">
          <div
            v-for="step in message.plan"
            :key="step.id"
            class="flex items-start gap-2 text-xs py-1.5 px-2 rounded-lg transition-colors"
            :class="[step.status === 'running' ? 'bg-cyan-50/70 dark:bg-cyan-950/30 text-cyan-900 dark:text-cyan-200' : 'text-gray-700 dark:text-zinc-300']"
          >
            <div class="mt-0.5 flex-shrink-0">
              <Loader2 v-if="step.status === 'running'" class="w-3.5 h-3.5 text-cyan-500 animate-spin" />
              <CheckCircle2 v-else-if="step.status === 'completed'" class="w-3.5 h-3.5 text-emerald-500" />
              <XCircle v-else-if="step.status === 'failed'" class="w-3.5 h-3.5 text-rose-500" />
              <Circle v-else class="w-3.5 h-3.5 text-gray-400" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-medium flex items-center gap-2">
                <span>{{ step.title }}</span>
                <span
                  class="text-[10px] px-1.5 py-0.2 rounded font-normal"
                  :class="[
                    step.status === 'running' ? 'bg-cyan-200/60 dark:bg-cyan-900/60 text-cyan-800 dark:text-cyan-200' :
                    step.status === 'completed' ? 'bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300' :
                    'bg-gray-100 dark:bg-zinc-800 text-gray-500'
                  ]"
                >
                  {{ step.status === 'running' ? '执行中' : step.status === 'completed' ? '已完成' : '待执行' }}
                </span>
              </div>
              <div v-if="step.description" class="text-[11px] text-gray-400 dark:text-zinc-500 truncate mt-0.5">
                {{ step.description }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 1. 最顶部的思考过程与内联极简工具调用（对标用户截图：用时 Xs 折叠条与单行极简工具） -->
      <ThinkingProcess
        v-if="hasThinkingOrTools"
        :thought="message.thought"
        :thought-duration="message.thoughtDuration"
        :tools="message.tools"
        :is-streaming="message.isStreaming"
        :has-content="Boolean(message.content && message.content.trim().length > 0)"
      />

      <!-- 异常错误通知栏 (带一键重试按钮) -->
      <div v-if="message.error" class="mb-3 p-3 rounded-xl bg-gray-50/90 dark:bg-zinc-900/70 border border-gray-200/90 dark:border-zinc-800 text-gray-700 dark:text-zinc-300 text-xs flex items-start justify-between gap-3 shadow-2xs">
        <div class="flex items-start gap-2 min-w-0">
          <AlertCircle class="w-4 h-4 text-gray-500 dark:text-zinc-400 flex-shrink-0 mt-0.5" />
          <div class="min-w-0">
            <div class="font-medium text-gray-800 dark:text-zinc-200">执行提示:</div>
            <div class="text-gray-600 dark:text-zinc-400 break-words">{{ message.error }}</div>
          </div>
        </div>
        <button
          @click="handleRegenerate"
          type="button"
          class="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-gray-300/80 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-gray-100 dark:hover:bg-zinc-700 text-[11px] font-medium text-gray-700 dark:text-zinc-300 transition-colors flex-shrink-0 cursor-pointer shadow-2xs"
          title="点击重新生成回答"
        >
          <RotateCcw class="w-3 h-3" />
          <span>重试</span>
        </button>
      </div>

      <!-- Markdown 正文渲染区 (支持代码块顶部专属一键复制) -->
      <div
        v-if="message.content"
        @click="handleMarkdownClick"
        class="markdown-body text-gray-800 dark:text-zinc-200 select-text"
        v-html="renderedMarkdown"
      ></div>



      <!-- 助手底部辅助操作栏（回答完成且存在正文时，悬停展示复制与重新生成按钮） -->
      <div
        v-if="message.content && !message.isStreaming"
        class="flex items-center gap-3 mt-2 min-h-6"
      >
        <div class="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            @click="copyText"
            class="flex items-center gap-1 text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300 px-1.5 py-0.5 rounded hover:bg-gray-100 dark:hover:bg-zinc-800 cursor-pointer transition-colors"
            title="复制回答内容"
          >
            <Check v-if="isCopied" class="w-3.5 h-3.5 text-gray-500 dark:text-zinc-400" />
            <Copy v-else class="w-3.5 h-3.5" />
            <span>{{ isCopied ? '已复制' : '复制' }}</span>
          </button>

          <button
            @click="handleRegenerate"
            class="flex items-center gap-1 text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300 px-1.5 py-0.5 rounded hover:bg-gray-100 dark:hover:bg-zinc-800 cursor-pointer transition-colors"
            title="重新生成此回答"
          >
            <RotateCcw class="w-3.5 h-3.5" />
            <span>重新生成</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 点击图片大图全屏预览遮罩 (Teleport 挂载到 body) -->
    <Teleport to="body">
      <div
        v-if="activePreviewImage"
        @click="activePreviewImage = null"
        class="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 cursor-zoom-out select-none"
      >
        <img
          :src="activePreviewImage"
          alt="大图全屏预览"
          class="max-w-[90vw] max-h-[90vh] rounded-2xl object-contain shadow-2xl"
          @click.stop
        />
      </div>
    </Teleport>
  </div>
</template>
