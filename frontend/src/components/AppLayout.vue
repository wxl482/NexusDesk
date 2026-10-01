<script setup lang="ts">
/**
 * 桌面客户端全局框架布局组件 (AppLayout)
 * 包含：可折叠侧边栏、品牌区、新会话按钮、各功能路由导航、历史会话切换、后端健康探活指示灯以及暗黑主题切换。
 */
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  BookOpen,
  Wrench,
  Settings as SettingsIcon,
  Plus,
  Trash2,
  Pencil,
} from 'lucide-vue-next'
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const settingsStore = useSettingsStore()

// 后端探活定时器句柄
let healthTimer: any = null

// 会话就地重命名状态管理
const editingSessionId = ref<string | null>(null)
const editingTitle = ref('')
const editInputRef = ref<HTMLInputElement | null>(null)

const startRenameSession = (session: { id: string; title: string }, e?: Event) => {
  e?.stopPropagation()
  editingSessionId.value = session.id
  editingTitle.value = session.title
  nextTick(() => {
    editInputRef.value?.focus()
    editInputRef.value?.select()
  })
}

const saveRenameSession = (sessionId: string) => {
  if (editingSessionId.value === sessionId) {
    if (editingTitle.value.trim()) {
      chatStore.renameSession(sessionId, editingTitle.value)
    }
    editingSessionId.value = null
  }
}

const cancelRename = () => {
  editingSessionId.value = null
}

// 自动更新状态管理 (electron-updater)
const updateState = ref<{
  hasUpdate: boolean
  isDownloaded: boolean
  version: string
  percent?: number
}>({
  hasUpdate: false,
  isDownloaded: false,
  version: '',
})

const handleApplyUpdate = () => {
  // @ts-ignore
  if (window.electronAPI?.quitAndInstallUpdate) {
    // @ts-ignore
    window.electronAPI.quitAndInstallUpdate()
  }
}

onMounted(() => {
  // 初始化首次会话并触发探活
  chatStore.initSession()
  settingsStore.checkBackendHealth()
  // 每 4 秒轮询一次后端健康检查
  healthTimer = setInterval(() => {
    settingsStore.checkBackendHealth()
  }, 4000)

  // 监听后台静默自动更新事件
  // @ts-ignore
  if (window.electronAPI?.onUpdaterMessage) {
    // @ts-ignore
    window.electronAPI.onUpdaterMessage((data: any) => {
      if (data.status === 'available') {
        updateState.value = {
          hasUpdate: true,
          isDownloaded: false,
          version: data.version,
        }
      } else if (data.status === 'downloading') {
        updateState.value.hasUpdate = true
        updateState.value.percent = data.percent
      } else if (data.status === 'downloaded') {
        updateState.value = {
          hasUpdate: true,
          isDownloaded: true,
          version: data.version,
        }
      }
    })
  }
})

onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
})

// 创建新会话并自动导航到对话工作台
const handleNewChat = () => {
  chatStore.createNewSession()
  if (route.path !== '/') {
    router.push('/')
  }
}

// 切换选中的历史会话
const handleSelectSession = (sessionId: string) => {
  chatStore.loadSessionMessages(sessionId)
  if (route.path !== '/') {
    router.push('/')
  }
}
</script>

<template>
  <div
    class="h-screen w-screen flex bg-gray-50 dark:bg-zinc-950 overflow-hidden text-gray-900 dark:text-zinc-100 select-none"
    :class="{ '!bg-transparent': route.path === '/quick-bar' }"
  >
    <!-- 侧边导航栏（包含对话列表）：在设置与快速小窗页面下完全隐藏 -->
    <aside
      v-if="route.path !== '/settings' && route.path !== '/quick-bar'"
      class="w-64 flex-shrink-0 flex flex-col border-r border-gray-200 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/60 backdrop-blur-md"
    >
      <!-- macOS 原生红绿灯专属空间与顶部拖拽条（仅保留红绿灯与原生窗口拖动支持） -->
      <div class="h-14 flex-shrink-0 border-b border-gray-100 dark:border-zinc-800/80 select-none window-drag-region"></div>

      <!-- 核心功能与操作导航清单（新建会话与智能助手等菜单保持一致 UI，选中与 hover 均使用纯粹灰色高亮） -->
      <nav class="px-3 py-2 space-y-1">
        <!-- 新建会话 -->
        <button
          @click="handleNewChat"
          type="button"
          class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-gray-600 dark:text-zinc-400 hover:bg-gray-200/80 dark:hover:bg-zinc-800 hover:text-gray-900 dark:hover:text-white active:bg-gray-300/80 dark:active:bg-zinc-700 transition-colors text-left cursor-pointer"
        >
          <Plus class="w-4 h-4" />
          <span>新建会话</span>
        </button>


        <router-link
          to="/rag"
          class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors"
          :class="[
            route.path === '/rag'
              ? 'bg-gray-200/80 dark:bg-zinc-800 text-gray-900 dark:text-white font-semibold'
              : 'text-gray-600 dark:text-zinc-400 hover:bg-gray-200/80 dark:hover:bg-zinc-800 hover:text-gray-900 dark:hover:text-white'
          ]"
        >
          <BookOpen class="w-4 h-4" />
          <span>知识库</span>
        </router-link>

        <router-link
          to="/tools"
          class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors"
          :class="[
            route.path === '/tools'
              ? 'bg-gray-200/80 dark:bg-zinc-800 text-gray-900 dark:text-white font-semibold'
              : 'text-gray-600 dark:text-zinc-400 hover:bg-gray-200/80 dark:hover:bg-zinc-800 hover:text-gray-900 dark:hover:text-white'
          ]"
        >
          <Wrench class="w-4 h-4" />
          <span>技能中心</span>
        </router-link>
      </nav>

      <!-- 历史会话分组标题 -->
      <div class="px-4 pt-3 pb-1 text-[11px] font-semibold text-gray-400 dark:text-zinc-500 uppercase tracking-wider">
        历史会话
      </div>
      <!-- 历史会话列表 -->
      <div class="flex-1 overflow-y-auto px-3 space-y-0.5">
        <div
          v-for="s in chatStore.sessions"
          :key="s.id"
          @click="handleSelectSession(s.id)"
          @dblclick="startRenameSession(s, $event)"
          class="group flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs cursor-pointer transition-colors relative"
          :class="[
            chatStore.currentSessionId === s.id
              ? 'bg-gray-200/80 dark:bg-zinc-800 text-gray-900 dark:text-white font-medium'
              : 'text-gray-600 dark:text-zinc-400 hover:bg-gray-200/80 dark:hover:bg-zinc-800 hover:text-gray-900 dark:hover:text-white'
          ]"
        >
          <!-- 正常显示模式 -->
          <template v-if="editingSessionId !== s.id">
            <span class="truncate flex-1" title="双击重命名">{{ s.title }}</span>
            <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                @click.stop="startRenameSession(s, $event)"
                class="p-0.5 text-gray-400 hover:text-gray-700 dark:hover:text-zinc-200 rounded transition-colors"
                title="重命名此会话 (或双击标题)"
              >
                <Pencil class="w-3 h-3" />
              </button>
              <button
                @click.stop="chatStore.deleteSession(s.id)"
                class="p-0.5 text-gray-400 hover:text-rose-500 rounded transition-colors"
                title="删除此会话"
              >
                <Trash2 class="w-3 h-3" />
              </button>
            </div>
          </template>

          <!-- 重命名编辑模式 -->
          <template v-else>
            <input
              ref="editInputRef"
              v-model="editingTitle"
              @click.stop
              @keydown.enter.stop="saveRenameSession(s.id)"
              @keydown.esc.stop="cancelRename"
              @blur="saveRenameSession(s.id)"
              type="text"
              class="w-full bg-white dark:bg-zinc-900 border border-gray-300 dark:border-zinc-700 rounded px-1.5 py-0.5 text-xs text-gray-900 dark:text-zinc-100 focus:outline-none focus:border-gray-500"
            />
          </template>
        </div>
      </div>

      <!-- 全自动静默更新就绪浮条 (electron-updater) -->
      <div
        v-if="updateState.hasUpdate"
        class="mx-2 mb-2 p-2.5 rounded-xl border border-indigo-200/80 dark:border-indigo-800/80 bg-indigo-50/90 dark:bg-indigo-950/40 text-xs space-y-1.5 shadow-sm"
      >
        <div class="flex items-center justify-between">
          <span class="font-bold text-indigo-700 dark:text-indigo-300 flex items-center gap-1">
            <span>🚀 发现新版本</span>
            <span class="font-mono text-[10px]">v{{ updateState.version }}</span>
          </span>
          <span v-if="!updateState.isDownloaded" class="text-[10px] text-indigo-500">
            下载中 {{ updateState.percent || 0 }}%
          </span>
        </div>
        <p class="text-[11px] text-gray-500 dark:text-zinc-400">
          {{ updateState.isDownloaded ? '更新包已静默就绪，重启即生效。' : '正在后台静默拉取更新包...' }}
        </p>
        <button
          v-if="updateState.isDownloaded"
          @click="handleApplyUpdate"
          class="w-full py-1 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-[11px] transition-colors cursor-pointer"
        >
          一键无感重启更新
        </button>
      </div>

      <!-- 底部系统设置入口 -->
      <div class="p-2 border-t border-gray-100 dark:border-zinc-800/80">
        <router-link
          to="/settings"
          class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors"
          :class="[
            route.path === '/settings'
              ? 'bg-gray-200/80 dark:bg-zinc-800 text-gray-900 dark:text-white font-semibold'
              : 'text-gray-600 dark:text-zinc-400 hover:bg-gray-200/80 dark:hover:bg-zinc-800 hover:text-gray-900 dark:hover:text-white'
          ]"
        >
          <SettingsIcon class="w-4 h-4" />
          <span>系统设置</span>
        </router-link>
      </div>
    </aside>

    <!-- 主展示工作区 -->
    <main class="flex-1 flex flex-col min-w-0 overflow-hidden relative">
      <router-view />
    </main>
  </div>
</template>
