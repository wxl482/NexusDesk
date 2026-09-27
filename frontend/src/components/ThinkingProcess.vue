<script setup lang="ts">
/**
 * 极简现代思考过程与工具调用内联展示组件 (ThinkingProcess)
 * 对标 DeepSeek-R1 / ChatGPT 官方交互风格：
 * 1. 位于助手每次回答的最顶部。
 * 2. 折叠状态：显示 "用时 36s  >"（流式中显示 "正在思考..."）。
 * 3. 展开状态：显示 "用时 36s  v"，下方展示思考正文，并将工具调用转化为极简单行（如 "🌐 已搜索网页 : https://..."）。
 * 4. 点击单行工具支持按需展开查看输入参数与执行输出。
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  Globe,
  Terminal,
  FileText,
  PenLine,
  Folder,
  BookOpen,
  Code2,
  Trash2,
  Wrench,
  ChevronRight,
  ChevronDown,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
} from 'lucide-vue-next'
import type { ToolCallItem } from '../stores/chat'

const props = defineProps<{
  /** 思考链正文 */
  thought?: string
  /** 思考用时（秒） */
  thoughtDuration?: number
  /** 工具调用列表 */
  tools?: ToolCallItem[]
  /** 当前助手回复是否正在流式生成中 */
  isStreaming?: boolean
  /** 当前助手回复是否已有正式正文生成 */
  hasContent?: boolean
}>()

// 用户是否主动点击过切换展开/折叠
const userToggled = ref(false)

// 默认折叠正在调用的工具与思考过程，用户需要查看时主动点击箭头展开
const isExpanded = ref(false)

// 记录哪个工具条目展开了详情
const expandedToolIds = ref<Set<string>>(new Set())

// 复制成功的提示控制
const copiedToolId = ref<string | null>(null)

// 动态实时计时器（用于流式思考中未出正文时的动态秒数展示）
const liveSeconds = ref(1)
let timerHandle: any = null

const startLiveTimer = () => {
  if (timerHandle) return
  liveSeconds.value = 1
  timerHandle = setInterval(() => {
    liveSeconds.value += 1
  }, 1000)
}

const stopLiveTimer = () => {
  if (timerHandle) {
    clearInterval(timerHandle)
    timerHandle = null
  }
}

onMounted(() => {
  if (props.isStreaming && !props.hasContent) {
    startLiveTimer()
  }
})

onUnmounted(() => {
  stopLiveTimer()
})

// 监听流式状态变化（默认保持折叠，用户想看自己点击箭头展开）
watch(
  () => [props.isStreaming, props.hasContent],
  ([streaming, hasContent]) => {
    if (!streaming || hasContent) {
      stopLiveTimer()
      if (!userToggled.value) {
        isExpanded.value = false
      }
    } else if (streaming && !hasContent) {
      startLiveTimer()
      if (!userToggled.value) {
        isExpanded.value = false
      }
    }
  }
)

// 切换思考过程的展开/折叠
const toggleExpanded = () => {
  userToggled.value = true
  isExpanded.value = !isExpanded.value
}

// 切换单个工具调用的详情展开
const toggleToolDetail = (toolId: string, e: Event) => {
  e.stopPropagation()
  if (expandedToolIds.value.has(toolId)) {
    expandedToolIds.value.delete(toolId)
  } else {
    expandedToolIds.value.add(toolId)
  }
}

// 复制工具输出内容
const copyToolOutput = async (toolId: string, content: string, e: Event) => {
  e.stopPropagation()
  try {
    await navigator.clipboard.writeText(content)
    copiedToolId.value = toolId
    setTimeout(() => {
      if (copiedToolId.value === toolId) copiedToolId.value = null
    }, 2000)
  } catch {}
}

// 过滤清洗掉决策卡片等不需要用户看到的系统内部信息（如 🎯 服务专家 等）
const cleanedThought = computed(() => {
  if (!props.thought) return ''
  return props.thought
    .replace(/🎯[\s\S]*?🛡️[^\n]*(?:\n+|$)/g, '')
    .trim()
})

// 格式化展示标题文本（如 "用时 36s" 或 "正在思考 (Xs)"，末尾不打省略号，保持右侧箭头前干净清爽）
const displayTitle = computed(() => {
  if (props.isStreaming && !props.hasContent) {
    return `正在思考 (${liveSeconds.value}s)`
  }
  if (props.thoughtDuration && props.thoughtDuration > 0) {
    const sec = Math.round(props.thoughtDuration)
    return `用时 ${sec > 0 ? sec : 1}s`
  }
  if (liveSeconds.value > 1) {
    return `用时 ${liveSeconds.value}s`
  }
  return '用时 1s'
})

// 将不同工具转换为统一的极简单行描述
const formatToolSummary = (tool: ToolCallItem) => {
  const name = (tool.name || '').toLowerCase()
  let inputObj: any = {}
  try {
    inputObj = typeof tool.input === 'string' ? JSON.parse(tool.input) : (tool.input || {})
  } catch {
    inputObj = { raw: tool.input }
  }

  // 1. 网络搜索
  if (name.includes('search')) {
    const query = inputObj.query || inputObj.url || inputObj.raw || ''
    return {
      type: 'search',
      icon: Globe,
      label: tool.status === 'running' ? '正在搜索网页' : (tool.status === 'error' ? '搜索网页异常' : '已搜索网页'),
      detail: query ? String(query) : '',
    }
  }

  // 2. 终端执行
  if (name.includes('terminal') || name.includes('shell') || name.includes('bash')) {
    const cmd = inputObj.command || inputObj.cmd || inputObj.raw || ''
    return {
      type: 'terminal',
      icon: Terminal,
      label: tool.status === 'running' ? '正在执行终端命令' : (tool.status === 'error' ? '终端命令失败' : '已执行终端命令'),
      detail: cmd ? String(cmd) : '',
    }
  }

  // 3. 读取本地文件
  if (name.includes('read_local') || name.includes('read_workspace') || name.includes('read_file')) {
    const path = inputObj.file_path || inputObj.path || inputObj.raw || ''
    return {
      type: 'read',
      icon: FileText,
      label: tool.status === 'running' ? '正在读取文件' : (tool.status === 'error' ? '读取文件失败' : '已读取文件'),
      detail: path ? String(path) : '',
    }
  }

  // 4. 写入本地文件
  if (name.includes('write_local') || name.includes('write_workspace') || name.includes('write_file')) {
    const path = inputObj.file_path || inputObj.path || inputObj.raw || ''
    return {
      type: 'write',
      icon: PenLine,
      label: tool.status === 'running' ? '正在写入文件' : (tool.status === 'error' ? '写入文件失败' : '已写入文件'),
      detail: path ? String(path) : '',
    }
  }

  // 5. 目录浏览
  if (name.includes('list_local') || name.includes('list_workspace') || name.includes('directory')) {
    const dir = inputObj.dir_path || inputObj.subdir || inputObj.raw || '.'
    return {
      type: 'dir',
      icon: Folder,
      label: tool.status === 'running' ? '正在浏览目录' : (tool.status === 'error' ? '浏览目录失败' : '已浏览目录'),
      detail: dir ? String(dir) : '',
    }
  }

  // 6. 删除文件
  if (name.includes('delete')) {
    const path = inputObj.file_path || inputObj.path || inputObj.raw || ''
    return {
      type: 'delete',
      icon: Trash2,
      label: tool.status === 'running' ? '正在删除文件' : (tool.status === 'error' ? '删除文件失败' : '已删除文件'),
      detail: path ? String(path) : '',
    }
  }

  // 7. 知识库检索
  if (name.includes('rag') || name.includes('knowledge')) {
    const query = inputObj.query || inputObj.raw || ''
    return {
      type: 'rag',
      icon: BookOpen,
      label: tool.status === 'running' ? '正在检索知识库' : (tool.status === 'error' ? '检索知识库失败' : '已检索知识库'),
      detail: query ? String(query) : '',
    }
  }

  // 8. Python 计算
  if (name.includes('python') || name.includes('code') || name.includes('calc')) {
    const code = inputObj.code || inputObj.raw || ''
    const shortCode = code.length > 50 ? code.slice(0, 50) + '...' : code
    return {
      type: 'python',
      icon: Code2,
      label: tool.status === 'running' ? '正在运行代码计算' : (tool.status === 'error' ? '代码计算执行失败' : '已运行代码计算'),
      detail: shortCode ? String(shortCode) : '',
    }
  }

  // 兜底通用
  return {
    type: 'generic',
    icon: Wrench,
    label: tool.status === 'running' ? `正在调用 ${tool.name}` : `已调用 ${tool.name}`,
    detail: '',
  }
}
</script>

<template>
  <div class="thinking-process-block w-full mb-3 select-none">
    <!-- 1. 顶部触发折叠栏（完全对齐截图 1 & 2） -->
    <div
      @click="toggleExpanded"
      class="inline-flex items-center gap-1.5 py-1 text-[14px] text-gray-500 dark:text-zinc-400 hover:text-gray-800 dark:hover:text-zinc-200 cursor-pointer transition-colors group/header"
    >
      <!-- 动态呼吸点（仅在流式思考且未出正文时显示） -->
      <span
        v-if="isStreaming && !hasContent"
        class="inline-block w-2 h-2 rounded-full bg-gray-400 dark:bg-zinc-500 animate-pulse flex-shrink-0"
      ></span>

      <!-- 标题文本：例如 "用时 36s" 或 "正在思考..." -->
      <span class="font-normal tracking-wide text-[14px]">{{ displayTitle }}</span>

      <!-- 右侧指示箭头：折叠时为 >，展开时为 v -->
      <ChevronDown
        v-if="isExpanded"
        class="w-4 h-4 text-gray-400 group-hover/header:text-gray-600 dark:group-hover/header:text-zinc-300 transition-transform"
      />
      <ChevronRight
        v-else
        class="w-4 h-4 text-gray-400 group-hover/header:text-gray-600 dark:group-hover/header:text-zinc-300 transition-transform"
      />
    </div>

    <!-- 2. 展开后的内容区域（完全对标截图 2：思考正文 + 极简单行工具调用） -->
    <div
      v-if="isExpanded"
      class="mt-1 pl-1 pt-1 space-y-2 border-l-2 border-gray-200/70 dark:border-zinc-800 ml-1 select-text transition-all"
    >
      <!-- 思考链思维过程文本 (DeepSeek-R1 等) -->
      <div
        v-if="cleanedThought"
        class="text-[13px] text-gray-700 dark:text-zinc-300 leading-relaxed font-normal whitespace-pre-wrap select-text pl-2"
      >
        {{ cleanedThought }}
      </div>

      <!-- 正在思考跳动占位符（当流式中且既无 thought 也无 tools 时） -->
      <div
        v-else-if="isStreaming && !hasContent && (!tools || tools.length === 0)"
        class="flex items-center gap-1.5 py-1 pl-2 text-xs text-gray-400 font-mono"
      >
        <span class="inline-block w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-zinc-500 animate-bounce"></span>
        <span class="inline-block w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-zinc-500 animate-bounce [animation-delay:0.2s]"></span>
        <span class="inline-block w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-zinc-500 animate-bounce [animation-delay:0.4s]"></span>
        <span class="text-xs text-gray-400 ml-1">梳理任务脉络与调度策略...</span>
      </div>

      <!-- 极简工具调用清单（对标截图 2：🌐 已搜索网页 : https://...） -->
      <div v-if="tools && tools.length > 0" class="space-y-1 pt-1 pl-2">
        <div
          v-for="t in tools"
          :key="t.id"
          class="group/tool flex flex-col rounded-lg transition-colors"
        >
          <!-- 单行极简展示行 -->
          <div
            @click="toggleToolDetail(t.id, $event)"
            class="flex items-center gap-2 py-0.5 text-xs sm:text-[13px] text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 cursor-pointer select-text"
            :title="expandedToolIds.has(t.id) ? '点击折叠执行详情' : '点击查看执行参数与结果'"
          >
            <!-- 工具图标 -->
            <component
              :is="formatToolSummary(t).icon"
              class="w-3.5 h-3.5 flex-shrink-0 text-gray-500 dark:text-zinc-400"
            />

            <!-- 操作动作标签：如 "已搜索网页 :" -->
            <span class="font-normal flex-shrink-0 text-gray-700 dark:text-zinc-300">
              {{ formatToolSummary(t).label }} :
            </span>

            <!-- 具体目标/参数：如 "https://github.com/..." -->
            <span
              v-if="formatToolSummary(t).detail"
              class="truncate font-mono text-[12px] text-gray-600 dark:text-zinc-400 max-w-[500px]"
            >
              {{ formatToolSummary(t).detail }}
            </span>

            <!-- 运行状态指示器 -->
            <div class="flex items-center gap-1.5 ml-auto pl-2 flex-shrink-0">
              <Loader2
                v-if="t.status === 'running'"
                class="w-3 h-3 text-gray-400 animate-spin"
              />
              <AlertCircle
                v-else-if="t.status === 'error'"
                class="w-3 h-3 text-rose-500"
                title="执行失败"
              />
              <!-- 微型展开角标 -->
              <ChevronRight
                class="w-3 h-3 text-gray-400/60 opacity-0 group-hover/tool:opacity-100 transition-all"
                :class="{ 'rotate-90': expandedToolIds.has(t.id) }"
              />
            </div>
          </div>

          <!-- 点击展开的工具执行参数与输出详情抽屉 (按需极简展开) -->
          <div
            v-if="expandedToolIds.has(t.id)"
            class="my-1.5 p-2.5 rounded-xl bg-gray-50 dark:bg-zinc-900/80 border border-gray-200/80 dark:border-zinc-800 text-xs space-y-2 select-text font-mono shadow-2xs"
          >
            <!-- 输入参数 -->
            <div v-if="t.input">
              <div class="text-[11px] font-semibold text-gray-500 dark:text-zinc-400 uppercase tracking-wider mb-1">
                Input Args
              </div>
              <pre class="p-2 rounded bg-white dark:bg-zinc-800/80 border border-gray-100 dark:border-zinc-700 text-gray-700 dark:text-zinc-300 text-[11px] overflow-x-auto whitespace-pre-wrap max-h-40">{{ typeof t.input === 'object' ? JSON.stringify(t.input, null, 2) : t.input }}</pre>
            </div>

            <!-- 输出结果 -->
            <div v-if="t.output">
              <div class="flex items-center justify-between text-[11px] font-semibold text-gray-500 dark:text-zinc-400 uppercase tracking-wider mb-1">
                <span>Output Result</span>
                <button
                  @click="copyToolOutput(t.id, t.output, $event)"
                  type="button"
                  class="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-700 dark:text-zinc-400 dark:hover:text-zinc-200 cursor-pointer"
                >
                  <Check v-if="copiedToolId === t.id" class="w-3 h-3 text-emerald-500" />
                  <Copy v-else class="w-3 h-3" />
                  <span>{{ copiedToolId === t.id ? '已复制' : '复制' }}</span>
                </button>
              </div>
              <pre class="p-2 rounded bg-white dark:bg-zinc-800/80 border border-gray-100 dark:border-zinc-700 text-gray-700 dark:text-zinc-300 text-[11px] overflow-x-auto whitespace-pre-wrap max-h-60">{{ t.output }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.thinking-process-block {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
</style>
