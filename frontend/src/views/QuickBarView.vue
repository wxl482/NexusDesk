<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import {
  Search,
  Sparkles,
  ExternalLink,
  X,
  Clipboard,
  Languages,
  Globe,
  FolderSync,
  CornerDownLeft,
  ArrowRight,
  Copy,
  Check,
} from 'lucide-vue-next'
import { SSEChatClient } from '../api/sse'
import { useSettingsStore } from '../stores/settings'

const query = ref('')
const isStreaming = ref(false)
const quickResponse = ref('')
const selectedMode = ref<'chat' | 'react' | 'rag'>('chat')
const inputRef = ref<HTMLInputElement | null>(null)
const settingsStore = useSettingsStore()
const sseClient = new SSEChatClient()
const isCopied = ref(false)

const handleEsc = () => {
  if (isStreaming.value) {
    sseClient.abort()
    isStreaming.value = false
    return
  }
  // @ts-ignore
  if (window.electronAPI?.hideQuickBar) {
    // @ts-ignore
    window.electronAPI.hideQuickBar()
  }
}

const handleOpenInMain = () => {
  const q = query.value.trim()
  // @ts-ignore
  if (window.electronAPI?.openInMainWindow) {
    // @ts-ignore
    window.electronAPI.openInMainWindow(q)
  }
}

// 快速动作 1：读取系统剪贴板并分析
const handleReadClipboard = async () => {
  let clipText = ''
  // @ts-ignore
  if (window.electronAPI?.readClipboardText) {
    // @ts-ignore
    clipText = await window.electronAPI.readClipboardText()
  } else {
    try {
      clipText = await navigator.clipboard.readText()
    } catch (_) {}
  }
  if (clipText.trim()) {
    query.value = `分析并解释剪贴板内容：${clipText.slice(0, 300)}${clipText.length > 300 ? '...' : ''}`
    handleQuerySubmit()
  }
}

// 快速动作 2：中英文快捷互译
const handleQuickTranslate = async () => {
  let text = query.value.trim()
  if (!text) {
    // @ts-ignore
    if (window.electronAPI?.readClipboardText) {
      // @ts-ignore
      text = await window.electronAPI.readClipboardText()
    }
  }
  if (text) {
    query.value = `中英互译：${text}`
    handleQuerySubmit()
  }
}

// 快速动作 3：全网快搜
const handleQuickSearch = () => {
  selectedMode.value = 'react'
  if (query.value.trim()) {
    handleQuerySubmit()
  } else {
    query.value = '实时联网搜索：'
    inputRef.value?.focus()
  }
}

// 快速动作 4：工作区文件调用
const handleWorkspaceScan = () => {
  selectedMode.value = 'react'
  if (query.value.trim()) {
    query.value = `扫描工作区文件并回答：${query.value}`
  } else {
    query.value = '扫描本地工作区文件：'
  }
  inputRef.value?.focus()
}

const handleCopyResult = async () => {
  if (!quickResponse.value) return
  await navigator.clipboard.writeText(quickResponse.value)
  isCopied.value = true
  setTimeout(() => {
    isCopied.value = false
  }, 2000)
}

const handleQuerySubmit = async () => {
  const q = query.value.trim()
  if (!q || isStreaming.value) return

  quickResponse.value = ''
  isStreaming.value = true

  await sseClient.streamChat(
    {
      message: q,
      session_id: 'quickbar_' + Date.now(),
      mode: selectedMode.value,
      model: settingsStore.model,
      base_url: settingsStore.baseUrl,
      api_key: settingsStore.apiKey,
      temperature: 0.3,
    },
    {
      onToken: (token) => {
        quickResponse.value += token
      },
      onThought: () => {},
      onToolStart: () => {},
      onToolEnd: () => {},
      onNodeChange: () => {},
      onError: (err) => {
        quickResponse.value += `\n\n[错误]: ${err}`
        isStreaming.value = false
      },
      onDone: () => {
        isStreaming.value = false
      },
    }
  )
}

const handleKeyDown = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    handleEsc()
  } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    handleOpenInMain()
  } else if (e.key === 'Enter' && !e.shiftKey) {
    handleQuerySubmit()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  nextTick(() => {
    inputRef.value?.focus()
  })
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})
</script>

<template>
  <div class="h-full w-full p-2 flex flex-col justify-start items-center select-none bg-transparent">
    <div
      class="w-full max-w-[660px] bg-white/95 dark:bg-zinc-900/95 backdrop-blur-2xl rounded-2xl border border-gray-200/90 dark:border-zinc-700/80 shadow-[0_25px_70px_-15px_rgba(0,0,0,0.4)] overflow-hidden transition-all duration-150 flex flex-col"
      :class="[quickResponse ? 'max-h-[440px]' : 'max-h-[175px]']"
    >
      <!-- 搜索主输入行 -->
      <div class="h-14 flex items-center px-4 gap-3 border-b border-gray-100 dark:border-zinc-800/80 window-drag-region">
        <div class="w-7 h-7 rounded-xl bg-gradient-to-tr from-indigo-500 to-cyan-500 flex items-center justify-center flex-shrink-0 shadow-sm">
          <Sparkles class="w-4 h-4 text-white" />
        </div>

        <input
          ref="inputRef"
          v-model="query"
          type="text"
          placeholder="呼唤 NexusDesk (查剪贴板 / 翻译 / 快搜 / 工作区文件... Esc 收起)"
          class="flex-1 bg-transparent text-sm text-gray-900 dark:text-zinc-100 placeholder-gray-400 dark:placeholder-zinc-500 outline-none window-no-drag"
        />

        <div class="flex items-center gap-1.5 window-no-drag">
          <button
            @click="handleOpenInMain"
            type="button"
            class="px-2 py-1 rounded-md text-[11px] font-medium text-gray-500 hover:text-gray-900 dark:text-zinc-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors flex items-center gap-1 cursor-pointer"
            title="在主工作区展开此对话 (⌘+Enter)"
          >
            <ExternalLink class="w-3 h-3" />
            <span>主窗口</span>
          </button>

          <button
            @click="handleEsc"
            type="button"
            class="p-1 rounded-md text-gray-400 hover:text-gray-700 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- 快捷动作胶囊栏（Raycast 风格） -->
      <div class="px-3.5 py-1.5 bg-gray-50/70 dark:bg-zinc-950/40 flex items-center gap-1.5 border-b border-gray-100 dark:border-zinc-800/60 window-no-drag overflow-x-auto text-[11px]">
        <button
          @click="handleReadClipboard"
          class="flex items-center gap-1 px-2 py-0.5 rounded-md border border-gray-200/80 dark:border-zinc-700/80 bg-white dark:bg-zinc-800/80 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 text-gray-600 dark:text-zinc-300 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors cursor-pointer"
        >
          <Clipboard class="w-3 h-3 text-indigo-500" />
          <span>查剪贴板</span>
        </button>

        <button
          @click="handleQuickTranslate"
          class="flex items-center gap-1 px-2 py-0.5 rounded-md border border-gray-200/80 dark:border-zinc-700/80 bg-white dark:bg-zinc-800/80 hover:bg-blue-50 dark:hover:bg-blue-950/40 text-gray-600 dark:text-zinc-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors cursor-pointer"
        >
          <Languages class="w-3 h-3 text-blue-500" />
          <span>快捷翻译</span>
        </button>

        <button
          @click="handleQuickSearch"
          class="flex items-center gap-1 px-2 py-0.5 rounded-md border border-gray-200/80 dark:border-zinc-700/80 bg-white dark:bg-zinc-800/80 hover:bg-cyan-50 dark:hover:bg-cyan-950/40 text-gray-600 dark:text-zinc-300 hover:text-cyan-600 dark:hover:text-cyan-400 transition-colors cursor-pointer"
        >
          <Globe class="w-3 h-3 text-cyan-500" />
          <span>全网快搜</span>
        </button>

        <button
          @click="handleWorkspaceScan"
          class="flex items-center gap-1 px-2 py-0.5 rounded-md border border-gray-200/80 dark:border-zinc-700/80 bg-white dark:bg-zinc-800/80 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 text-gray-600 dark:text-zinc-300 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors cursor-pointer"
        >
          <FolderSync class="w-3 h-3 text-emerald-500" />
          <span>工作区文件</span>
        </button>

        <div class="ml-auto flex items-center gap-2 text-[10px] text-gray-400 dark:text-zinc-500">
          <span>↵ 发送</span>
          <span>•</span>
          <span>⌘↵ 打开主窗口</span>
        </div>
      </div>

      <!-- 流式回答展开区 -->
      <div v-if="quickResponse || isStreaming" class="flex-1 overflow-y-auto p-4 text-xs text-gray-800 dark:text-zinc-200 leading-relaxed font-sans select-text window-no-drag space-y-2">
        <div class="flex items-center justify-between pb-1 border-b border-gray-100 dark:border-zinc-800/60">
          <span class="text-[10px] font-semibold text-gray-400">Agent 即时回复:</span>
          <button
            @click="handleCopyResult"
            class="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-700 dark:hover:text-zinc-200 cursor-pointer"
          >
            <component :is="isCopied ? Check : Copy" class="w-3 h-3" :class="{ 'text-emerald-500': isCopied }" />
            <span>{{ isCopied ? '已复制' : '复制结果' }}</span>
          </button>
        </div>
        <div class="whitespace-pre-wrap">{{ quickResponse }}</div>
        <div v-if="isStreaming" class="flex items-center gap-1.5 text-indigo-500 pt-1">
          <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping"></span>
          <span class="text-[11px]">正在分析执行并输出...</span>
        </div>
      </div>
    </div>
  </div>
</template>
