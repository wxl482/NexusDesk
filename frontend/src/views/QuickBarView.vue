<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import {
  Search,
  Sparkles,
  ExternalLink,
  X,
  CornerDownLeft,
  Terminal,
  Globe,
  BookOpen,
  ArrowRight,
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
      class="w-full max-w-[660px] bg-white/90 dark:bg-zinc-900/90 backdrop-blur-2xl rounded-2xl border border-gray-200/90 dark:border-zinc-700/80 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.35)] overflow-hidden transition-all duration-150 flex flex-col"
      :class="[quickResponse ? 'max-h-[420px]' : 'max-h-[140px]']"
    >
      <!-- 搜索主输入行 -->
      <div class="h-14 flex items-center px-4 gap-3 border-b border-gray-100 dark:border-zinc-800/80 window-drag-region">
        <div class="w-7 h-7 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center flex-shrink-0 shadow-sm">
          <Sparkles class="w-4 h-4 text-white" />
        </div>

        <input
          ref="inputRef"
          v-model="query"
          type="text"
          placeholder="向 NexusDesk 闪念提问、指令搜索... (Esc 关闭)"
          class="flex-1 bg-transparent text-sm text-gray-900 dark:text-zinc-100 placeholder-gray-400 dark:placeholder-zinc-500 outline-none window-no-drag"
        />

        <div class="flex items-center gap-1.5 window-no-drag">
          <button
            @click="handleOpenInMain"
            type="button"
            class="px-2 py-1 rounded-md text-[11px] font-medium text-gray-500 hover:text-gray-900 dark:text-zinc-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors flex items-center gap-1"
            title="在主工作区展开此对话 (⌘+Enter)"
          >
            <ExternalLink class="w-3 h-3" />
            <span>主窗口</span>
          </button>

          <button
            @click="handleEsc"
            type="button"
            class="p-1 rounded-md text-gray-400 hover:text-gray-700 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- 快捷模式指示与提示条 -->
      <div class="px-4 py-2 bg-gray-50/60 dark:bg-zinc-950/40 flex items-center justify-between text-[11px] text-gray-400 dark:text-zinc-500 border-b border-gray-100 dark:border-zinc-800/60 window-no-drag">
        <div class="flex items-center gap-2">
          <button
            @click="selectedMode = 'chat'"
            class="px-2 py-0.5 rounded-full transition-colors font-medium"
            :class="[selectedMode === 'chat' ? 'bg-cyan-500/15 text-cyan-600 dark:text-cyan-400' : 'hover:bg-gray-200/60 dark:hover:bg-zinc-800']"
          >
            极速对话
          </button>
          <button
            @click="selectedMode = 'react'"
            class="px-2 py-0.5 rounded-full transition-colors font-medium"
            :class="[selectedMode === 'react' ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400' : 'hover:bg-gray-200/60 dark:hover:bg-zinc-800']"
          >
            全能 Agent
          </button>
          <button
            @click="selectedMode = 'rag'"
            class="px-2 py-0.5 rounded-full transition-colors font-medium"
            :class="[selectedMode === 'rag' ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' : 'hover:bg-gray-200/60 dark:hover:bg-zinc-800']"
          >
            知识库检索
          </button>
        </div>

        <div class="flex items-center gap-2">
          <span>↵ 发送提问</span>
          <span>•</span>
          <span>⌘↵ 跳转主窗口</span>
        </div>
      </div>

      <!-- 流式回答展开区 -->
      <div v-if="quickResponse || isStreaming" class="flex-1 overflow-y-auto p-4 text-xs text-gray-800 dark:text-zinc-200 leading-relaxed font-sans select-text window-no-drag">
        <div class="whitespace-pre-wrap">{{ quickResponse }}</div>
        <div v-if="isStreaming" class="flex items-center gap-1.5 text-cyan-500 mt-2">
          <span class="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-ping"></span>
          <span class="text-[11px]">思考响应中...</span>
        </div>
      </div>
    </div>
  </div>
</template>
