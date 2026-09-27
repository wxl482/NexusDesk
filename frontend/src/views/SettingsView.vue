<script setup lang="ts">
/**
 * 统一系统设置中心视图 (SettingsView)
 * 1:1 对标 macOS 原生 ChatGPT 桌面端设置 UI 规范：
 * - 紧凑双栏布局，无冗余顶部面包屑
 * - 纯净大标题与语义化分组卡片 (rounded-2xl divide-y)
 * - 原生级控件（iOS/macOS 风格 Toggle 开关、微型下拉药丸、分段选择器）
 * - 移除 ESC 监听与冗余关闭按钮，增大返回应用呼吸感
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Bot,
  BookOpen,
  Info,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertCircle,
  Radio,
  ExternalLink,
  ChevronDown,
  RefreshCw,
  Search,
  Check,
  ArrowLeft,
  Settings as GearIcon,
  Hand,
  ShieldCheck,
  AlertTriangle,
} from 'lucide-vue-next'
import { useSettingsStore } from '../stores/settings'
import { useChatStore } from '../stores/chat'
import { useRagStore } from '../stores/rag'
import { apiClient } from '../api/client'

const router = useRouter()
const settingsStore = useSettingsStore()
const chatStore = useChatStore()
const ragStore = useRagStore()

// 当前激活的设置选项卡：'preferences' | 'model' | 'rag' | 'about'
const activeTab = ref<'preferences' | 'model' | 'rag' | 'about'>('preferences')

// 搜索设置关键词
const settingsSearch = ref('')

// 分组导航项定义（参考 ChatGPT 桌面端设置排版）
const settingsGroups = [
  {
    title: '个人',
    items: [
      { id: 'preferences', name: '常规', icon: GearIcon, keywords: ['常规', '外观', '主题', '暗黑', '浅色', '明亮', '历史', '会话'] },
      { id: 'model', name: '模型与服务商', icon: Bot, keywords: ['模型', '服务商', 'api', 'key', '密钥', 'openai', 'deepseek', 'ollama', 'url', 'temperature', '温度'] },
      { id: 'rag', name: '知识库与检索', icon: BookOpen, keywords: ['知识库', 'rag', '检索', '向量', 'topk', 'chunk', '切块'] },
    ]
  },
  {
    title: '集成',
    items: [
      { id: 'about', name: '关于与服务状态', icon: Info, keywords: ['关于', '版本', '系统', '引擎', '后端', 'chroma', '状态', '诊断'] },
    ]
  }
]

// 实时搜索过滤分类菜单
const filteredGroups = computed(() => {
  const query = settingsSearch.value.trim().toLowerCase()
  if (!query) return settingsGroups
  return settingsGroups
    .map(g => ({
      ...g,
      items: g.items.filter(item =>
        item.name.toLowerCase().includes(query) ||
        item.keywords.some(k => k.toLowerCase().includes(query))
      )
    }))
    .filter(g => g.items.length > 0)
})

// 当前激活选项卡的中文名称（对齐参考图中的大标题）
const currentTabTitle = computed(() => {
  switch (activeTab.value) {
    case 'preferences': return '常规'
    case 'model': return '模型与服务商'
    case 'rag': return '知识库与检索'
    case 'about': return '关于与服务状态'
    default: return '设置'
  }
})

// 返回主工作区（优先历史回退）
const handleBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}

// 控制 API Key 密码明文切换
const showApiKey = ref(false)
// 测试连通性加载状态
const isTesting = ref(false)
// 模型列表搜索过滤关键字
const modelSearchQuery = ref('')

// 过滤后的模型列表
const filteredModels = computed(() => {
  const query = modelSearchQuery.value.trim().toLowerCase()
  const list = settingsStore.currentModels
  if (!query) return list
  return list.filter(m => m.id.toLowerCase().includes(query) || (m.owned_by && m.owned_by.toLowerCase().includes(query)))
})

// 模型下拉选择浮层控制
const isModelDropdownOpen = ref(false)
const modelDropdownRef = ref<HTMLElement | null>(null)

const handleSelectModel = (modelId: string) => {
  settingsStore.setModel(modelId)
  isModelDropdownOpen.value = false
  triggerSaveToast()
}

// 批准策略下拉浮层控制
const isApprovalDropdownOpen = ref(false)
const approvalDropdownRef = ref<HTMLElement | null>(null)

// 批准策略折叠按钮显示文本
const currentApprovalButtonLabel = computed(() => {
  switch (settingsStore.approvalMode) {
    case 'ask_always':
      return '按请求'
    case 'smart':
      return '帮我批准'
    case 'full_access':
      return '完全访问'
    default:
      return '按请求'
  }
})

// 选择批准策略
const selectApprovalMode = (mode: 'ask_always' | 'smart' | 'full_access') => {
  settingsStore.setApprovalMode(mode)
  isApprovalDropdownOpen.value = false
  triggerSaveToast()
}

// 点击外部区域自动关闭下拉框
const handleDocumentClick = (e: MouseEvent) => {
  if (modelDropdownRef.value && !modelDropdownRef.value.contains(e.target as Node)) {
    isModelDropdownOpen.value = false
  }
  if (approvalDropdownRef.value && !approvalDropdownRef.value.contains(e.target as Node)) {
    isApprovalDropdownOpen.value = false
  }
}

// 触发拉取最新模型列表
const handleFetchModels = async () => {
  const res = await settingsStore.fetchModels()
  if (res?.success && settingsStore.currentModels.length > 0) {
    isModelDropdownOpen.value = true
  }
}

// 连通性测试结果
const testResult = ref<{ success?: boolean; message?: string; reply?: string; error?: string } | null>(null)
// 保存成功的轻量提示
const showSaveSuccess = ref(false)

onMounted(() => {
  ragStore.fetchDocuments()
  settingsStore.checkBackendHealth()
  settingsStore.fetchProviders()
  window.addEventListener('click', handleDocumentClick)
})

onUnmounted(() => {
  window.removeEventListener('click', handleDocumentClick)
})

// 触发保存提示
const triggerSaveToast = () => {
  settingsStore.save()
  showSaveSuccess.value = true
  setTimeout(() => {
    showSaveSuccess.value = false
  }, 2000)
}

// 保存设置
const handleSave = () => {
  triggerSaveToast()
}

// 唤起外部默认浏览器打开链接
const openExternalLink = (url?: string) => {
  if (!url) return
  if ((window as any).electronAPI?.openExternal) {
    ;(window as any).electronAPI.openExternal(url)
  } else {
    window.open(url, '_blank')
  }
}

// 验证模型连接连通性
const handleTestConnection = async () => {
  isTesting.value = true
  testResult.value = null
  try {
    const res = await apiClient.testModel({
      model: settingsStore.model,
      base_url: settingsStore.baseUrl,
      api_key: settingsStore.apiKey,
    })
    testResult.value = res
  } catch (err: any) {
    testResult.value = {
      success: false,
      error: err.message || '连接失败，请检查网络连接或接口配置。',
    }
  } finally {
    isTesting.value = false
  }
}

// 清空知识库所有文档
const handleClearRag = async () => {
  if (confirm('确认清空知识库中的所有资料吗？此操作不可逆。')) {
    try {
      await apiClient.clearRag()
      await ragStore.fetchDocuments()
      alert('知识库已成功清空。')
    } catch (e: any) {
      alert('清空知识库失败: ' + (e.message || '未知错误'))
    }
  }
}

// 清空所有历史会话
const handleClearHistory = () => {
  if (confirm('确认清空所有历史对话记录吗？所有本地聊天记录将被清除。')) {
    chatStore.clearAllSessions()
    alert('已成功清空所有历史会话记录。')
  }
}
</script>

<template>
  <div class="flex-1 flex h-full bg-white dark:bg-zinc-950 overflow-hidden select-none">
    
    <!-- 左侧：设置分类导航侧边栏（对标 ChatGPT 桌面端设置侧边栏） -->
    <aside class="w-60 flex-shrink-0 flex flex-col border-r border-gray-200/80 dark:border-zinc-800 bg-[#fbfbfb] dark:bg-zinc-900/60 backdrop-blur-md">
      <!-- 顶部 macOS 原生红绿灯拖拽留白区 -->
      <div class="h-10 flex-shrink-0 window-drag-region select-none"></div>

      <!-- 返回应用按钮行（增大上外边距与内边距，提升呼吸感） -->
      <div class="px-4 pt-2 pb-4 select-none">
        <button
          @click="handleBack"
          class="flex items-center gap-2 text-[13px] font-medium text-gray-700 dark:text-zinc-300 hover:text-gray-950 dark:hover:text-white transition-colors cursor-pointer group"
          title="返回应用"
        >
          <ArrowLeft class="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
          <span>返回应用</span>
        </button>
      </div>

      <!-- 搜索设置输入框（药丸形状，对标参考图中的圆角搜索胶囊） -->
      <div class="px-3 pb-3 select-none">
        <div class="relative">
          <Search class="w-3.5 h-3.5 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            v-model="settingsSearch"
            placeholder="搜索设置..."
            class="w-full pl-9 pr-7 py-1.5 rounded-full bg-black/[0.04] dark:bg-white/[0.07] hover:bg-black/[0.06] dark:hover:bg-white/[0.1] focus:bg-white dark:focus:bg-zinc-900 border border-transparent focus:border-gray-300 dark:focus:border-zinc-700 text-xs text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none transition-all"
          />
          <button
            v-if="settingsSearch"
            @click="settingsSearch = ''"
            class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-zinc-200 text-xs p-0.5"
          >
            ✕
          </button>
        </div>
      </div>

      <!-- 分组分类导航选项（间距与字号完全匹配参考图） -->
      <nav class="flex-1 overflow-y-auto px-3 py-1 space-y-4">
        <div
          v-for="(group, gIdx) in filteredGroups"
          :key="group.title"
          :class="[gIdx > 0 ? 'mt-4 pt-1' : 'mt-0.5']"
        >
          <!-- 分组标题（如 "个人"、"集成"） -->
          <div class="px-3 pb-1 text-xs text-gray-400 dark:text-zinc-500 font-normal select-none">
            {{ group.title }}
          </div>

          <!-- 组内菜单项列表 -->
          <div class="space-y-0.5">
            <button
              v-for="item in group.items"
              :key="item.id"
              @click="activeTab = item.id as any"
              type="button"
              class="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-xl text-left text-[13px] leading-5 transition-colors cursor-pointer select-none"
              :class="[
                activeTab === item.id
                  ? 'bg-black/[0.06] dark:bg-white/[0.09] text-gray-900 dark:text-white font-medium'
                  : 'text-gray-600 dark:text-zinc-400 hover:bg-black/[0.03] dark:hover:bg-white/[0.05] hover:text-gray-900 dark:hover:text-white'
              ]"
            >
              <component :is="item.icon" class="w-4 h-4 flex-shrink-0 text-gray-500 dark:text-zinc-400" />
              <span class="truncate">{{ item.name }}</span>
            </button>
          </div>
        </div>

        <div v-if="filteredGroups.length === 0" class="py-8 text-center text-xs text-gray-400 dark:text-zinc-500">
          未找到相关设置项
        </div>
      </nav>

      <!-- 底部引擎状态小徽章 -->
      <div class="p-3 border-t border-gray-100 dark:border-zinc-800/80 text-xs">
        <div class="flex items-center gap-2 px-1 text-[11px] text-gray-500 dark:text-zinc-400">
          <span
            class="w-2 h-2 rounded-full"
            :class="[settingsStore.backendOnline ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]' : 'bg-amber-500 animate-pulse']"
          ></span>
          <span>{{ settingsStore.backendOnline ? 'AI 引擎就绪' : '连接后端引擎...' }}</span>
        </div>
      </div>
    </aside>

    <!-- 右侧：对应设置页面内容容器（纯净背景，对齐 macOS ChatGPT 原生设置窗口） -->
    <main class="flex-1 flex flex-col h-full overflow-hidden select-text bg-white dark:bg-zinc-950">
      <!-- 顶部 macOS 窗口拖拽区域（无任何面包屑、无分割线，保持整洁开阔） -->
      <div class="h-10 flex-shrink-0 window-drag-region select-none"></div>

      <!-- 设置内容滚动区 -->
      <div class="flex-1 overflow-y-auto px-8 md:px-12 pb-16">
        <div class="max-w-2xl space-y-6">

          <!-- 顶部大标题（完全对齐参考图中的 "常规"） -->
          <div>
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight">
              {{ currentTabTitle }}
            </h1>
          </div>

          <!-- 保存成功浮动小提示 -->
          <transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0 translate-y-1" enter-to-class="opacity-100 translate-y-0" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100" leave-to-class="opacity-0">
            <div v-if="showSaveSuccess" class="p-2.5 px-4 rounded-xl bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 text-gray-700 dark:text-zinc-200 text-xs flex items-center gap-2">
              <CheckCircle2 class="w-4 h-4" />
              <span>配置已自动保存并生效</span>
            </div>
          </transition>

          <!-- 页面 1：常规偏好 (activeTab === 'preferences') -->
          <div v-if="activeTab === 'preferences'" class="space-y-6">
            <!-- 分区 1: 外观 -->
            <div>
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">外观</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden divide-y divide-gray-100 dark:divide-zinc-800/80 shadow-2xs">
                <!-- 暗黑模式 Toggle -->
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">深色暗黑外观</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">切换明亮或深色暗黑桌面视觉风格</div>
                  </div>
                  <!-- iOS / macOS 风格切换开关 -->
                  <button
                    type="button"
                    @click="settingsStore.toggleDark()"
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
                    :class="[settingsStore.isDark ? 'bg-gray-800 dark:bg-zinc-500' : 'bg-gray-200 dark:bg-zinc-700']"
                    role="switch"
                    :aria-checked="settingsStore.isDark"
                  >
                    <span
                      class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                      :class="[settingsStore.isDark ? 'translate-x-5' : 'translate-x-0']"
                    />
                  </button>
                </div>
              </div>
            </div>

            <!-- 分区 2: 操作权限与审批模式 -->
            <div class="relative z-20">
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">权限</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xs">
                <div class="px-5 py-3.5 flex items-center justify-between gap-4 relative rounded-2xl">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">批准策略</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">选择智能体何时请求批准</div>
                  </div>

                  <!-- 批准策略选择下拉按钮（对标 macOS 原生设置药丸控件） -->
                  <div ref="approvalDropdownRef" class="relative flex-shrink-0">
                    <button
                      @click.stop="isApprovalDropdownOpen = !isApprovalDropdownOpen"
                      type="button"
                      class="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-gray-50 dark:hover:bg-zinc-700/80 text-xs font-medium text-gray-800 dark:text-zinc-200 flex items-center gap-1.5 shadow-2xs transition-colors cursor-pointer"
                      :class="[settingsStore.approvalMode === 'full_access' ? 'text-[#E06714] dark:text-[#F97316] border-amber-300/70 dark:border-amber-700/60' : '']"
                    >
                      <span>{{ currentApprovalButtonLabel }}</span>
                      <ChevronDown class="w-3.5 h-3.5 text-gray-400 transition-transform" :class="{ 'rotate-180': isApprovalDropdownOpen }" />
                    </button>

                    <!-- 下拉选择菜单 (Popover) -->
                    <div
                      v-if="isApprovalDropdownOpen"
                      class="absolute right-0 top-full mt-2 w-80 sm:w-96 rounded-2xl border border-gray-200/90 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-2xl z-50 p-2 space-y-1 select-none animate-in fade-in slide-in-from-top-1 duration-150"
                    >
                      <!-- 模式 1: 请求批准 -->
                      <button
                        @click="selectApprovalMode('ask_always')"
                        type="button"
                        class="w-full p-2.5 rounded-xl flex items-start justify-between gap-3 text-left transition-colors cursor-pointer"
                        :class="[
                          settingsStore.approvalMode === 'ask_always'
                            ? 'bg-black/[0.05] dark:bg-white/[0.08]'
                            : 'hover:bg-black/[0.02] dark:hover:bg-white/[0.04]'
                        ]"
                      >
                        <div class="flex items-start gap-3 min-w-0">
                          <div class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 bg-gray-100 dark:bg-zinc-800 text-gray-700 dark:text-zinc-300 mt-0.5">
                            <Hand class="w-3.5 h-3.5" />
                          </div>
                          <div class="min-w-0">
                            <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">请求批准</div>
                            <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5 leading-relaxed">写入文件与终端命令执行前询问（联网搜索与文件读取直接执行）</div>
                          </div>
                        </div>
                        <Check v-if="settingsStore.approvalMode === 'ask_always'" class="w-4 h-4 text-gray-900 dark:text-white flex-shrink-0 mt-1" />
                      </button>

                      <!-- 模式 2: 帮我批准 -->
                      <button
                        @click="selectApprovalMode('smart')"
                        type="button"
                        class="w-full p-2.5 rounded-xl flex items-start justify-between gap-3 text-left transition-colors cursor-pointer"
                        :class="[
                          settingsStore.approvalMode === 'smart'
                            ? 'bg-black/[0.05] dark:bg-white/[0.08]'
                            : 'hover:bg-black/[0.02] dark:hover:bg-white/[0.04]'
                        ]"
                      >
                        <div class="flex items-start gap-3 min-w-0">
                          <div class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 bg-gray-100 dark:bg-zinc-800 text-gray-700 dark:text-zinc-300 mt-0.5">
                            <ShieldCheck class="w-3.5 h-3.5" />
                          </div>
                          <div class="min-w-0">
                            <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">帮我批准</div>
                            <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5 leading-relaxed">仅对删除文件与破坏性系统命令请求批准（默认推荐）</div>
                          </div>
                        </div>
                        <Check v-if="settingsStore.approvalMode === 'smart'" class="w-4 h-4 text-gray-900 dark:text-white flex-shrink-0 mt-1" />
                      </button>

                      <!-- 模式 3: 完全访问权限 -->
                      <button
                        @click="selectApprovalMode('full_access')"
                        type="button"
                        class="w-full p-2.5 rounded-xl flex items-start justify-between gap-3 text-left transition-colors cursor-pointer"
                        :class="[
                          settingsStore.approvalMode === 'full_access'
                            ? 'bg-amber-500/[0.08] dark:bg-amber-500/[0.12]'
                            : 'hover:bg-black/[0.02] dark:hover:bg-white/[0.04]'
                        ]"
                      >
                        <div class="flex items-start gap-3 min-w-0">
                          <div class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 bg-amber-50 dark:bg-amber-950/40 text-[#E06714] dark:text-[#F97316] mt-0.5">
                            <AlertTriangle class="w-3.5 h-3.5" />
                          </div>
                          <div class="min-w-0">
                            <div class="text-[13px] font-semibold text-[#E06714] dark:text-[#F97316]">完全访问权限</div>
                            <div class="text-xs text-[#E06714]/85 dark:text-[#F97316]/85 mt-0.5 leading-relaxed">完全自主调度所有工具，不弹出任何确认卡片</div>
                          </div>
                        </div>
                        <Check v-if="settingsStore.approvalMode === 'full_access'" class="w-4 h-4 text-[#E06714] dark:text-[#F97316] flex-shrink-0 mt-1" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 分区 3: 数据与会话 -->
            <div>
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">数据与记录</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden divide-y divide-gray-100 dark:divide-zinc-800/80 shadow-2xs">
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">本地历史会话记录</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">当前已在本地安全缓存 {{ chatStore.sessions.length }} 个会话</div>
                  </div>
                  <button
                    @click="handleClearHistory"
                    type="button"
                    class="px-3.5 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:border-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-rose-600 dark:text-rose-400 text-xs font-medium transition-colors shadow-2xs cursor-pointer flex-shrink-0"
                  >
                    清空历史
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 页面 2：AI 模型与服务商配置 (activeTab === 'model') -->
          <div v-else-if="activeTab === 'model'" class="space-y-6">
            <!-- 分区 1: 模型选择 -->
            <div class="relative z-30">
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">模型配置</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 divide-y divide-gray-100 dark:divide-zinc-800/80 shadow-2xs">
                <!-- 1. 服务商 Row -->
                <div class="px-5 py-3.5 flex items-center justify-between gap-4 rounded-t-2xl">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">服务商</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">选择大语言模型服务提供商</div>
                  </div>
                  <div class="relative flex-shrink-0">
                    <select
                      :value="settingsStore.currentProviderId"
                      @change="settingsStore.selectProvider(($event.target as HTMLSelectElement).value); triggerSaveToast()"
                      class="appearance-none pl-3 pr-8 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs font-medium text-gray-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-gray-400 dark:focus:ring-zinc-500 cursor-pointer shadow-2xs hover:bg-gray-50 dark:hover:bg-zinc-700/80 transition-colors"
                    >
                      <option v-for="p in settingsStore.providers" :key="p.id" :value="p.id">
                        {{ p.name }}
                      </option>
                    </select>
                    <ChevronDown class="w-3.5 h-3.5 text-gray-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                  </div>
                </div>

                <!-- 2. 当前模型 Combobox Row -->
                <div class="px-5 py-3.5 flex items-center justify-between gap-4 relative rounded-b-2xl">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">当前模型</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">选择或直接输入模型标识</div>
                  </div>

                  <div class="flex items-center gap-2 relative flex-shrink-0">
                    <div ref="modelDropdownRef" class="relative">
                      <div class="flex items-center">
                        <input
                          :value="settingsStore.model"
                          @input="settingsStore.setModel(($event.target as HTMLInputElement).value); triggerSaveToast()"
                          @focus="isModelDropdownOpen = true"
                          type="text"
                          placeholder="输入或选择模型..."
                          class="w-48 sm:w-56 pl-3 pr-8 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs font-mono font-medium text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-gray-400 dark:focus:ring-zinc-500 shadow-2xs"
                        />
                        <button
                          @click.stop="isModelDropdownOpen = !isModelDropdownOpen"
                          type="button"
                          class="absolute right-2 text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300 p-0.5 cursor-pointer"
                          title="查看/选择可用模型"
                        >
                          <ChevronDown class="w-3.5 h-3.5 transition-transform" :class="{ 'rotate-180': isModelDropdownOpen }" />
                        </button>
                      </div>

                      <!-- 搜索下拉菜单 (Popover) -->
                      <div
                        v-if="isModelDropdownOpen"
                        class="absolute right-0 top-full mt-2 w-72 sm:w-80 rounded-xl border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-2xl z-50 p-2 space-y-2 select-none animate-in fade-in slide-in-from-top-1 duration-150"
                      >
                        <div class="relative">
                          <Search class="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                          <input
                            v-model="modelSearchQuery"
                            type="text"
                            placeholder="搜索模型..."
                            class="w-full pl-8 pr-6 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-zinc-800 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-gray-400 dark:focus:border-zinc-500"
                            @click.stop
                          />
                          <button
                            v-if="modelSearchQuery"
                            @click.stop="modelSearchQuery = ''"
                            class="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs"
                          >
                            ✕
                          </button>
                        </div>

                        <div class="max-h-56 overflow-y-auto space-y-0.5 pr-0.5">
                          <div
                            v-for="m in filteredModels"
                            :key="m.id"
                            @click="handleSelectModel(m.id)"
                            class="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs cursor-pointer transition-colors"
                            :class="[
                              settingsStore.model === m.id
                                ? 'bg-gray-100 dark:bg-zinc-800 text-gray-900 dark:text-zinc-100 font-semibold'
                                : 'text-gray-700 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-800'
                            ]"
                          >
                            <span class="font-mono truncate" :title="m.id">{{ m.id }}</span>
                            <Check v-if="settingsStore.model === m.id" class="w-3.5 h-3.5 text-gray-700 dark:text-zinc-200 flex-shrink-0" />
                          </div>

                          <div v-if="filteredModels.length === 0" class="py-4 text-center text-xs text-gray-400 dark:text-zinc-500">
                            {{ settingsStore.currentModels.length === 0 ? '尚未拉取模型，可点击右侧刷新按钮' : '未找到匹配模型' }}
                          </div>
                        </div>

                        <div class="border-t border-gray-100 dark:border-zinc-800 pt-1.5 flex items-center justify-between text-[11px] text-gray-400 px-1">
                          <span>共 {{ settingsStore.currentModels.length }} 个模型</span>
                          <button
                            @click.stop="handleFetchModels"
                            :disabled="settingsStore.isFetchingModels"
                            class="text-gray-600 dark:text-zinc-300 hover:underline flex items-center gap-1 font-medium disabled:opacity-50 cursor-pointer"
                          >
                            <RefreshCw class="w-3 h-3" :class="{ 'animate-spin': settingsStore.isFetchingModels }" />
                            <span>{{ settingsStore.isFetchingModels ? '拉取中...' : '重新拉取' }}</span>
                          </button>
                        </div>
                      </div>
                    </div>

                    <!-- 实时拉取模型刷新按钮 -->
                    <button
                      @click.stop="handleFetchModels"
                      :disabled="settingsStore.isFetchingModels"
                      class="p-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-gray-50 dark:hover:bg-zinc-700 text-gray-600 dark:text-zinc-300 transition-colors disabled:opacity-50 cursor-pointer shadow-2xs"
                      title="从当前服务商实时拉取可用模型列表"
                    >
                      <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': settingsStore.isFetchingModels }" />
                    </button>
                  </div>
                </div>
              </div>

              <!-- 拉取状态微反馈 -->
              <div v-if="settingsStore.fetchModelsSuccessMsg || settingsStore.fetchModelsError" class="mt-1.5 px-1 text-[11px]">
                <span v-if="settingsStore.fetchModelsSuccessMsg" class="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 class="w-3 h-3" />
                  {{ settingsStore.fetchModelsSuccessMsg }}
                </span>
                <span v-else-if="settingsStore.fetchModelsError" class="text-rose-600 dark:text-rose-400 flex items-center gap-1">
                  <AlertCircle class="w-3 h-3" />
                  {{ settingsStore.fetchModelsError }}
                </span>
              </div>
            </div>

            <!-- 分区 2: 接口与认证 -->
            <div>
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">接口与认证</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden divide-y divide-gray-100 dark:divide-zinc-800/80 shadow-2xs">
                <!-- API Key Row -->
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="flex items-center gap-1.5">
                      <span class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">API Key</span>
                      <button
                        v-if="settingsStore.currentProvider.keyUrl"
                        @click="openExternalLink(settingsStore.currentProvider.keyUrl)"
                        class="text-[11px] text-gray-600 dark:text-zinc-300 hover:underline inline-flex items-center gap-0.5 font-medium cursor-pointer"
                      >
                        <span>获取 Key</span>
                        <ExternalLink class="w-2.5 h-2.5" />
                      </button>
                    </div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">
                      {{ settingsStore.currentProvider.needKey ? '凭据加密保存在本机，按服务商独立记忆' : '本地离线服务，免密直接调用' }}
                    </div>
                  </div>

                  <div v-if="!settingsStore.currentProvider.needKey" class="flex items-center gap-1.5 text-xs text-gray-600 dark:text-zinc-300 bg-gray-100 dark:bg-zinc-800 px-2.5 py-1 rounded-lg border border-gray-200/70 dark:border-zinc-700/60 font-medium flex-shrink-0">
                    <CheckCircle2 class="w-3.5 h-3.5" />
                    <span>免密就绪 (默认端口 11434)</span>
                  </div>
                  <div v-else class="relative w-48 sm:w-64 flex-shrink-0">
                    <input
                      :value="settingsStore.apiKey"
                      @input="settingsStore.setApiKey(($event.target as HTMLInputElement).value); triggerSaveToast()"
                      :type="showApiKey ? 'text' : 'password'"
                      :placeholder="`请输入 ${settingsStore.currentProvider.name} Key`"
                      class="w-full pl-3 pr-8 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs font-mono text-gray-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-gray-400 dark:focus:ring-zinc-500 shadow-2xs"
                    />
                    <button
                      @click="showApiKey = !showApiKey"
                      type="button"
                      class="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300 cursor-pointer"
                    >
                      <EyeOff v-if="showApiKey" class="w-3.5 h-3.5" />
                      <Eye v-else class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <!-- Base URL Row -->
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">接口地址 (Base URL)</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">服务接口请求基础路径</div>
                  </div>
                  <div class="w-48 sm:w-64 flex-shrink-0">
                    <input
                      v-model="settingsStore.baseUrl"
                      @change="triggerSaveToast"
                      type="text"
                      class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs font-mono text-gray-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-gray-400 dark:focus:ring-zinc-500 shadow-2xs"
                    />
                  </div>
                </div>
              </div>
            </div>

            <!-- 分区 3: 推理参数 -->
            <div>
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">推理参数</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden divide-y divide-gray-100 dark:divide-zinc-800/80 shadow-2xs">
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">创造力偏好 (Temperature)</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">数值越小越严谨精准（适合办公与代码），数值越大越发散想象</div>
                  </div>
                  <div class="flex items-center gap-3 w-44 sm:w-56 flex-shrink-0">
                    <input
                      v-model.number="settingsStore.temperature"
                      @change="triggerSaveToast"
                      type="range"
                      min="0"
                      max="1.5"
                      step="0.05"
                      class="flex-1 cursor-pointer"
                      :style="{
                        background: `linear-gradient(to right, ${settingsStore.isDark ? '#3b82f6' : '#007aff'} 0%, ${settingsStore.isDark ? '#3b82f6' : '#007aff'} ${(settingsStore.temperature / 1.5) * 100}%, ${settingsStore.isDark ? '#27272a' : '#e5e7eb'} ${(settingsStore.temperature / 1.5) * 100}%, ${settingsStore.isDark ? '#27272a' : '#e5e7eb'} 100%)`
                      }"
                    />
                    <span class="w-10 text-center font-mono text-xs font-semibold text-gray-800 dark:text-zinc-200 bg-gray-100 dark:bg-zinc-800 py-0.5 rounded border border-gray-200 dark:border-zinc-700">
                      {{ settingsStore.temperature }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 底部操作与内联连通性指示器 -->
            <div class="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div class="flex items-center gap-2 text-xs">
                <span
                  class="w-2 h-2 rounded-full flex-shrink-0"
                  :class="[
                    isTesting
                      ? 'bg-amber-500 animate-pulse'
                      : testResult?.success
                        ? 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.5)]'
                        : testResult?.success === false
                          ? 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.5)]'
                          : 'bg-gray-300 dark:bg-zinc-600'
                  ]"
                ></span>

                <span v-if="isTesting" class="text-amber-600 dark:text-amber-400 font-medium">
                  正在验证接口连通性...
                </span>
                <span v-else-if="testResult?.success" class="text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1.5 truncate max-w-sm">
                  <span>连接正常</span>
                  <span v-if="testResult.reply" class="text-gray-400 dark:text-zinc-500 font-normal truncate" :title="testResult.reply">
                    (响应: "{{ testResult.reply }}")
                  </span>
                </span>
                <span v-else-if="testResult?.success === false" class="text-rose-600 dark:text-rose-400 font-medium truncate max-w-sm" :title="testResult.error">
                  连接失败: {{ testResult.error }}
                </span>
                <span v-else class="text-gray-400 dark:text-zinc-500">
                  配置更改将自动生效，点击右侧可测试连接
                </span>
              </div>

              <div class="flex items-center gap-2 flex-shrink-0">
                <button
                  @click="handleTestConnection"
                  :disabled="isTesting"
                  type="button"
                  class="px-3.5 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-gray-50 dark:hover:bg-zinc-700 text-gray-700 dark:text-zinc-200 text-xs font-medium transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer shadow-2xs"
                >
                  <Radio class="w-3.5 h-3.5" :class="{ 'animate-pulse text-gray-500 dark:text-zinc-400': isTesting }" />
                  <span>{{ isTesting ? '验证中...' : '测试连接' }}</span>
                </button>

                <button
                  @click="handleSave"
                  type="button"
                  class="px-4 py-1.5 rounded-lg bg-gray-900 hover:bg-gray-800 dark:bg-zinc-100 dark:hover:bg-white text-white dark:text-gray-900 text-xs font-medium transition-colors shadow-2xs cursor-pointer"
                >
                  保存配置
                </button>
              </div>
            </div>
          </div>

          <!-- 页面 3：知识库参数与存储配置 (activeTab === 'rag') -->
          <div v-else-if="activeTab === 'rag'" class="space-y-6">
            <!-- 分区 1: 检索参数 -->
            <div>
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">检索调优</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden divide-y divide-gray-100 dark:divide-zinc-800/80 shadow-2xs">
                <!-- Top-K Row -->
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">单次参考切片数 (Top K)</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">决定智能体每次回答时检索注入几段最相关的知识库文档切片</div>
                  </div>
                  <div class="flex items-center gap-3 w-44 sm:w-56 flex-shrink-0">
                    <input
                      v-model.number="settingsStore.ragTopK"
                      @change="triggerSaveToast"
                      type="range"
                      min="2"
                      max="8"
                      step="1"
                      class="flex-1 cursor-pointer"
                      :style="{
                        background: `linear-gradient(to right, ${settingsStore.isDark ? '#3b82f6' : '#007aff'} 0%, ${settingsStore.isDark ? '#3b82f6' : '#007aff'} ${((settingsStore.ragTopK - 2) / 6) * 100}%, ${settingsStore.isDark ? '#27272a' : '#e5e7eb'} ${((settingsStore.ragTopK - 2) / 6) * 100}%, ${settingsStore.isDark ? '#27272a' : '#e5e7eb'} 100%)`
                      }"
                    />
                    <span class="w-12 text-center font-mono text-xs font-semibold text-gray-800 dark:text-zinc-200 bg-gray-100 dark:bg-zinc-800 py-0.5 rounded border border-gray-200 dark:border-zinc-700">
                      {{ settingsStore.ragTopK }} 条
                    </span>
                  </div>
                </div>

                <!-- Chunk Size Row -->
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">文档分块大小 (Chunk Size)</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">导入新文档时单个分块的字符数，兼顾段落完整性与检索精确度</div>
                  </div>
                  <div class="inline-flex rounded-lg bg-gray-100 dark:bg-zinc-800 p-0.5 text-xs flex-shrink-0">
                    <button
                      v-for="size in [300, 500, 800]"
                      :key="size"
                      @click="settingsStore.ragChunkSize = size; triggerSaveToast()"
                      type="button"
                      class="px-2.5 py-1 rounded-md font-medium transition-all cursor-pointer"
                      :class="[
                        settingsStore.ragChunkSize === size
                          ? 'bg-white dark:bg-zinc-700 text-gray-900 dark:text-white shadow-2xs font-semibold'
                          : 'text-gray-500 dark:text-zinc-400 hover:text-gray-800 dark:hover:text-zinc-200'
                      ]"
                    >
                      {{ size === 300 ? '300字' : (size === 500 ? '500字 (推荐)' : '800字') }}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 分区 2: 存储管理 -->
            <div>
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">知识库存储</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden divide-y divide-gray-100 dark:divide-zinc-800/80 shadow-2xs">
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">已收录知识库文档</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">当前知识库已收录并在本地向量库建立索引 {{ ragStore.documents.length }} 篇文档</div>
                  </div>
                  <button
                    @click="handleClearRag"
                    type="button"
                    class="px-3.5 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:border-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-rose-600 dark:text-rose-400 text-xs font-medium transition-colors shadow-2xs cursor-pointer flex-shrink-0"
                  >
                    清空知识库
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 页面 4：关于与系统状态 (activeTab === 'about') -->
          <div v-else-if="activeTab === 'about'" class="space-y-6">
            <!-- 分区 1: 软件与系统 -->
            <div>
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">软件与架构</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden divide-y divide-gray-100 dark:divide-zinc-800/80 shadow-2xs">
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">客户端版本</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">NexusDesk 智能体桌面工作台 (NexusDesk AI Workstation)</div>
                  </div>
                  <span class="text-xs font-mono font-medium text-gray-500 dark:text-zinc-400">v1.0.0</span>
                </div>

                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">底层调度引擎</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">支持自主调度、工具回调与上下文记忆流</div>
                  </div>
                  <span class="text-xs font-medium text-gray-800 dark:text-zinc-200">LangChain & LangGraph</span>
                </div>
              </div>
            </div>

            <!-- 分区 2: 本地服务状况 -->
            <div>
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2.5">本地运行环境</h2>
              <div class="rounded-2xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden divide-y divide-gray-100 dark:divide-zinc-800/80 shadow-2xs">
                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">智能体后端进程</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">FastAPI 本地服务 (http://127.0.0.1:8000)</div>
                  </div>
                  <div class="flex items-center gap-1.5 text-xs font-medium" :class="settingsStore.backendOnline ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-500'">
                    <span class="w-2 h-2 rounded-full" :class="settingsStore.backendOnline ? 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.5)]' : 'bg-amber-500 animate-pulse'"></span>
                    <span>{{ settingsStore.backendOnline ? '就绪运行中' : '连接后端中' }}</span>
                  </div>
                </div>

                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">本地向量数据库</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">用于文档分块持久化与余弦相似度召回</div>
                  </div>
                  <span class="text-xs font-medium text-gray-800 dark:text-zinc-200">Chroma 离线引擎</span>
                </div>

                <div class="px-5 py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div class="text-[13px] font-semibold text-gray-900 dark:text-zinc-100">数据与隐私安全</div>
                    <div class="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">历史对话记录与知识库向量均完全隔离存储于本机</div>
                  </div>
                  <span class="text-xs font-medium text-gray-600 dark:text-zinc-300">本地离线优先 · 安全沙箱</span>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </main>
  </div>
</template>
