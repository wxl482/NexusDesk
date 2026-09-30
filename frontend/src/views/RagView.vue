<script setup lang="ts">
/**
 * 本地知识库 (RAG) 管理视图
 * 具备拖拽多格式文件解析入库、多阶段实时进度条追踪、直接录入文本笔记、集合列表浏览与删除、以及语义相似度检索测试台。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import {
  Upload,
  FileText,
  Search,
  Trash2,
  Plus,
  RefreshCw,
  FileCheck,
  Loader2,
  AlertCircle,
  ShieldCheck,
  Download,
  RotateCcw,
  CheckCircle2,
  X,
} from 'lucide-vue-next'
import { useRagStore } from '../stores/rag'

const message = useMessage()
const ragStore = useRagStore()

// 当前激活的选项卡：'files' 文件集合 | 'text' 录入文本 | 'search' 检索测试 | 'backup' 灾备快照
const activeTab = ref<'files' | 'text' | 'search' | 'backup'>('files')
// 文件输入框 DOM 引用
const fileInput = ref<HTMLInputElement | null>(null)
// 录入文本表单数据
const textTitle = ref('')
const textContent = ref('')
const isSubmittingText = ref(false)

// 检索测试关键词与加载状态
const searchQuery = ref('')
const isSearching = ref(false)

// 灾备恢复/导出的加载状态
const isRestoring = ref(false)
const isExporting = ref(false)

// ========================
// 进度条交互与多阶段状态设计
// ========================
interface UploadTask {
  file: File
  fileName: string
  fileSizeText: string
  progress: number // 0 - 100
  stage: 'uploading' | 'parsing' | 'chunking' | 'indexing' | 'completed' | 'error'
  stageText: string
  chunks?: number
  errorMessage?: string
}

const currentTask = ref<UploadTask | null>(null)
const queueFiles = ref<File[]>([])
const currentFileIndex = ref(0)
const totalFilesCount = ref(0)

const isUploading = computed(() => {
  if (!currentTask.value) return false
  return currentTask.value.stage !== 'completed' && currentTask.value.stage !== 'error'
})

const stages = [
  { id: 'uploading', name: '文件传输', desc: '上传本地文件' },
  { id: 'parsing', name: '正文解析', desc: '提取文本与表格' },
  { id: 'chunking', name: '语义切片', desc: '双层父子分块' },
  { id: 'indexing', name: '向量入库', desc: '构建多维索引' },
]

const stageOrder = ['uploading', 'parsing', 'chunking', 'indexing', 'completed']

const isStagePassed = (stageId: string) => {
  if (!currentTask.value || currentTask.value.stage === 'error') return false
  const currentIdx = stageOrder.indexOf(currentTask.value.stage)
  const targetIdx = stageOrder.indexOf(stageId)
  return currentIdx > targetIdx
}

const isStageCurrent = (stageId: string) => {
  return currentTask.value?.stage === stageId
}

// 格式化文件体积大小
const formatFileSize = (bytes: number): string => {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// 获取各格式专属的图标色彩与标签
const getFileExtStyle = (filename: string) => {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  if (['pdf'].includes(ext)) {
    return {
      bg: 'bg-red-50 dark:bg-red-950/40',
      text: 'text-red-500 dark:text-red-400',
      border: 'border-red-200/80 dark:border-red-800/50',
      tag: 'PDF',
    }
  }
  if (['docx', 'doc'].includes(ext)) {
    return {
      bg: 'bg-blue-50 dark:bg-blue-950/40',
      text: 'text-blue-500 dark:text-blue-400',
      border: 'border-blue-200/80 dark:border-blue-800/50',
      tag: 'Word',
    }
  }
  if (['xlsx', 'xls', 'xlsm'].includes(ext)) {
    return {
      bg: 'bg-emerald-50 dark:bg-emerald-950/40',
      text: 'text-emerald-500 dark:text-emerald-400',
      border: 'border-emerald-200/80 dark:border-emerald-800/50',
      tag: 'Excel',
    }
  }
  if (['csv', 'tsv'].includes(ext)) {
    return {
      bg: 'bg-amber-50 dark:bg-amber-950/40',
      text: 'text-amber-500 dark:text-amber-400',
      border: 'border-amber-200/80 dark:border-amber-800/50',
      tag: 'CSV',
    }
  }
  if (['md', 'markdown'].includes(ext)) {
    return {
      bg: 'bg-purple-50 dark:bg-purple-950/40',
      text: 'text-purple-500 dark:text-purple-400',
      border: 'border-purple-200/80 dark:border-purple-800/50',
      tag: 'MD',
    }
  }
  return {
    bg: 'bg-indigo-50 dark:bg-indigo-950/40',
    text: 'text-indigo-500 dark:text-indigo-400',
    border: 'border-indigo-200/80 dark:border-indigo-800/50',
    tag: ext.toUpperCase() || 'FILE',
  }
}

// 灾备快照更新时间的可读化展示
const formatBackupTime = (val?: string | null) => {
  if (!val) return '未知'
  const num = Number(val)
  const date = Number.isFinite(num) && String(val).trim() !== '' ? new Date(num * 1000) : new Date(val)
  return Number.isNaN(date.getTime()) ? String(val) : date.toLocaleString()
}

onMounted(() => {
  ragStore.fetchDocuments()
  ragStore.fetchBackupStatus()
})

let simulatedTicker: any = null
let autoResetTimer: any = null

const clearTicker = () => {
  if (simulatedTicker) {
    clearInterval(simulatedTicker)
    simulatedTicker = null
  }
}

onUnmounted(() => {
  clearTicker()
  if (autoResetTimer) {
    clearTimeout(autoResetTimer)
    autoResetTimer = null
  }
})

// 重置上传面板为就绪状态
const resetUploadState = () => {
  if (autoResetTimer) {
    clearTimeout(autoResetTimer)
    autoResetTimer = null
  }
  clearTicker()
  currentTask.value = null
  queueFiles.value = []
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

// 启动后端计算阶段的平滑阶段轮询与渐进进度条模拟
const startBackendProcessingTicker = () => {
  clearTicker()
  if (!currentTask.value) return
  currentTask.value.stage = 'parsing'
  currentTask.value.stageText = '正在提取正文与多维结构化表格...'

  simulatedTicker = setInterval(() => {
    if (!currentTask.value || currentTask.value.stage === 'completed' || currentTask.value.stage === 'error') {
      clearTicker()
      return
    }
    if (currentTask.value.progress < 58) {
      currentTask.value.stage = 'parsing'
      currentTask.value.stageText = '正在解析文档格式与多维数据表...'
      currentTask.value.progress += 3
    } else if (currentTask.value.progress < 78) {
      currentTask.value.stage = 'chunking'
      currentTask.value.stageText = '正在进行双层父子语义切片 (Parent-Child)...'
      currentTask.value.progress += 2
    } else if (currentTask.value.progress < 94) {
      currentTask.value.stage = 'indexing'
      currentTask.value.stageText = '正在计算向量特征并同步构建 Milvus 与 BM25 索引...'
      currentTask.value.progress += 1
    }
  }, 280)
}

// 逐个处理上传文件队列
const processNextInQueue = async () => {
  if (queueFiles.value.length === 0) return
  const file = queueFiles.value.shift()!
  currentFileIndex.value = totalFilesCount.value - queueFiles.value.length

  currentTask.value = {
    file,
    fileName: file.name,
    fileSizeText: formatFileSize(file.size),
    progress: 5,
    stage: 'uploading',
    stageText: '正在上传本地文件...',
  }

  // 1. 网络上传进度回调 (映射至整体进度的 5% ~ 35%)
  const onUploadProgress = (percent: number) => {
    if (!currentTask.value || currentTask.value.stage !== 'uploading') return
    const mapped = Math.min(35, Math.max(5, Math.round(percent * 0.35)))
    currentTask.value.progress = mapped
    currentTask.value.stageText = `正在上传本地文件 (${percent}%)...`

    if (percent >= 100) {
      startBackendProcessingTicker()
    }
  }

  try {
    const res = await ragStore.uploadFile(file, onUploadProgress)
    clearTicker()

    if (res.success) {
      currentTask.value.progress = 100
      currentTask.value.stage = 'completed'
      currentTask.value.chunks = res.chunks || 0
      currentTask.value.stageText = `入库成功！已生成 ${res.chunks || 0} 个切片`

      // 若队列中还有待处理文件，延迟 1 秒后自动处理下一个
      if (queueFiles.value.length > 0) {
        setTimeout(() => {
          processNextInQueue()
        }, 1200)
      } else {
        // 全部完成：4 秒后自动淡出重置为上传区域，或者用户可以随时点击“继续添加”
        autoResetTimer = setTimeout(() => {
          resetUploadState()
        }, 4000)
      }
    } else {
      currentTask.value.stage = 'error'
      currentTask.value.errorMessage = res.message || '文件上传或解析失败'
      currentTask.value.stageText = '解析入库失败'
    }
  } catch (err: any) {
    clearTicker()
    if (currentTask.value) {
      currentTask.value.stage = 'error'
      currentTask.value.errorMessage = err.message || '网络连接或服务异常'
      currentTask.value.stageText = '解析入库失败'
    }
  }
}

// 接收多文件批次并推进处理
const processFiles = async (files: File[]) => {
  if (!files || files.length === 0) return
  if (isUploading.value) return

  if (autoResetTimer) {
    clearTimeout(autoResetTimer)
    autoResetTimer = null
  }

  queueFiles.value = [...files]
  totalFilesCount.value = files.length
  currentFileIndex.value = 0

  await processNextInQueue()
}

// 触发隐藏的系统原生文件选择器
const triggerFileSelect = () => {
  fileInput.value?.click()
}

// 处理点击选择上传的文件
const handleFileChange = (e: Event) => {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    processFiles(Array.from(target.files))
  }
}

// 处理拖拽放入文件
const handleDrop = (e: DragEvent) => {
  e.preventDefault()
  if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
    processFiles(Array.from(e.dataTransfer.files))
  }
}

// 提交录入的纯文本/Markdown 笔记
const handleTextSubmit = async () => {
  if (!textContent.value.trim() || isSubmittingText.value) {
    if (!textContent.value.trim()) message.warning('请输入笔记正文内容')
    return
  }
  isSubmittingText.value = true
  try {
    const res = await ragStore.uploadText(textTitle.value || '自定义笔记', textContent.value)
    if (res.success) {
      message.success(res.message, { duration: 3000 })
      textTitle.value = ''
      textContent.value = ''
      activeTab.value = 'files'
    } else {
      message.error(res.message, { duration: 5000 })
    }
  } finally {
    isSubmittingText.value = false
  }
}

// 删除知识库文档
const handleDeleteDoc = async (docId: string, title: string) => {
  const ok = await ragStore.deleteDocument(docId)
  if (ok) {
    message.success(`已彻底移除文档《${title}》`)
  } else {
    message.error('删除文档失败')
  }
}

// 执行向量语义相似度搜索
const handleSearch = async () => {
  if (!searchQuery.value.trim()) return
  isSearching.value = true
  await ragStore.search(searchQuery.value)
  isSearching.value = false
}

// 【方案 C 灾备】手动从快照恢复并重建向量库
const handleRestoreBackup = async () => {
  if (isRestoring.value) return
  isRestoring.value = true
  const loadingMsg = message.loading('正在从灾备快照重建向量库...', { duration: 0 })
  try {
    const res = await ragStore.restoreBackup()
    message.success(res.message || '灾备恢复完成', { duration: 5000 })
  } catch (err: any) {
    message.error(err.response?.data?.detail || '灾备恢复失败', { duration: 6000 })
  } finally {
    loadingMsg.destroy()
    isRestoring.value = false
  }
}

// 【方案 C 灾备】导出全量灾备包
const handleExportBackup = async () => {
  if (isExporting.value) return
  isExporting.value = true
  const loadingMsg = message.loading('正在导出全量灾备包...', { duration: 0 })
  try {
    const res = await ragStore.exportBackup()
    message.success(`${res.message}（${res.exported_file}）`, { duration: 6000 })
  } catch (err: any) {
    message.error(err.response?.data?.detail || '导出灾备包失败', { duration: 6000 })
  } finally {
    loadingMsg.destroy()
    isExporting.value = false
  }
}
</script>

<template>
  <div class="flex-1 flex flex-col h-full bg-gray-50/50 dark:bg-zinc-950 p-6 overflow-y-auto">
    <div class="max-w-5xl mx-auto w-full space-y-6">
      <!-- 页面顶部标题与操作 (支持无边框窗口拖拽) -->
      <div class="flex items-center justify-between pb-4 border-b border-gray-200 dark:border-zinc-800 window-drag-region select-none">
        <div class="window-no-drag">
          <h1 class="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            知识库中心
          </h1>
          <p class="text-xs text-gray-500 dark:text-zinc-400 mt-1">
            集中管理你的专属资料与私有文档。智能助手在回答问题时会自动查阅这些内容，提供精准答案与参考依据。
          </p>
        </div>

        <div class="flex items-center gap-2.5 window-no-drag">
          <!-- 刷新按钮 -->
          <button
            @click="ragStore.fetchDocuments"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-gray-50 text-xs font-medium text-gray-700 dark:text-zinc-300 transition-colors cursor-pointer"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': ragStore.isLoading }" />
            <span>刷新</span>
          </button>
        </div>
      </div>

      <!-- 功能选项卡切换 -->
      <div class="flex items-center gap-2 border-b border-gray-200 dark:border-zinc-800 text-xs">
        <button
          @click="activeTab = 'files'"
          class="pb-2 px-3 font-semibold transition-colors border-b-2 cursor-pointer"
          :class="[activeTab === 'files' ? 'border-gray-900 dark:border-zinc-100 text-gray-900 dark:text-zinc-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-zinc-300']"
        >
          已存文档 ({{ ragStore.documents.length }})
        </button>
        <button
          @click="activeTab = 'text'"
          class="pb-2 px-3 font-semibold transition-colors border-b-2 cursor-pointer"
          :class="[activeTab === 'text' ? 'border-gray-900 dark:border-zinc-100 text-gray-900 dark:text-zinc-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-zinc-300']"
        >
          添加笔记与纯文本
        </button>
        <button
          @click="activeTab = 'search'"
          class="pb-2 px-3 font-semibold transition-colors border-b-2 cursor-pointer"
          :class="[activeTab === 'search' ? 'border-gray-900 dark:border-zinc-100 text-gray-900 dark:text-zinc-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-zinc-300']"
        >
          内容检索预览
        </button>
        <button
          @click="activeTab = 'backup'; ragStore.fetchBackupStatus()"
          class="pb-2 px-3 font-semibold transition-colors border-b-2 cursor-pointer"
          :class="[activeTab === 'backup' ? 'border-gray-900 dark:border-zinc-100 text-gray-900 dark:text-zinc-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-zinc-300']"
        >
          灾备快照
        </button>
      </div>

      <!-- 选项卡 1：文档管理与拖拽上传 -->
      <div v-if="activeTab === 'files'" class="space-y-6">
        <!-- 上传区域：闲置拖拽区 OR 进度条多阶段交互卡片 -->
        
        <!-- 1. 正在上传或处理完成/出错时的独立进度交互卡片 -->
        <div
          v-if="currentTask"
          class="border border-indigo-200/90 dark:border-indigo-800/60 bg-white dark:bg-zinc-900 rounded-2xl p-6 shadow-sm space-y-4 transition-all"
        >
          <!-- 头部：文件图标、文件名、大小、队列指示、状态徽标与关闭按钮 -->
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-3 min-w-0">
              <div
                class="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 border"
                :class="[getFileExtStyle(currentTask.fileName).bg, getFileExtStyle(currentTask.fileName).text, getFileExtStyle(currentTask.fileName).border]"
              >
                <FileText class="w-5 h-5" />
              </div>
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-bold text-gray-900 dark:text-white truncate max-w-[320px] sm:max-w-[450px]">
                    {{ currentTask.fileName }}
                  </span>
                  <span
                    v-if="totalFilesCount > 1"
                    class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-800/40"
                  >
                    队列 {{ currentFileIndex }} / {{ totalFilesCount }}
                  </span>
                </div>
                <div class="text-[11px] text-gray-400 dark:text-zinc-500 mt-0.5 flex items-center gap-2">
                  <span>{{ currentTask.fileSizeText }}</span>
                  <span>•</span>
                  <span
                    class="font-medium"
                    :class="{
                      'text-red-500 dark:text-red-400': currentTask.stage === 'error',
                      'text-emerald-600 dark:text-emerald-400': currentTask.stage === 'completed',
                      'text-indigo-600 dark:text-indigo-400': isUploading,
                    }"
                  >
                    {{ currentTask.stageText }}
                  </span>
                </div>
              </div>
            </div>

            <!-- 右侧：进度百分比徽标 & 关闭重置按钮 -->
            <div class="flex items-center gap-2.5 flex-shrink-0">
              <span
                class="font-mono text-xs font-bold px-2.5 py-1 rounded-full border transition-all"
                :class="{
                  'bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 border-emerald-200/80 dark:border-emerald-800/50': currentTask.stage === 'completed',
                  'bg-red-50 dark:bg-red-950/50 text-red-600 dark:text-red-400 border-red-200/80 dark:border-red-800/50': currentTask.stage === 'error',
                  'bg-indigo-50 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400 border-indigo-200/80 dark:border-indigo-800/50': isUploading,
                }"
              >
                {{ currentTask.progress }}%
              </span>

              <button
                v-if="!isUploading"
                @click="resetUploadState"
                class="p-1 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
                title="关闭"
              >
                <X class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- 现代平滑进度条 -->
          <div class="relative w-full h-2.5 bg-gray-100 dark:bg-zinc-800 rounded-full overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-300 ease-out relative"
              :class="{
                'bg-gradient-to-r from-emerald-500 to-teal-400': currentTask.stage === 'completed',
                'bg-red-500': currentTask.stage === 'error',
                'bg-gradient-to-r from-indigo-500 via-purple-500 to-indigo-600': isUploading,
              }"
              :style="{ width: `${currentTask.progress}%` }"
            >
              <!-- 正在运行时的光泽微流光动画 -->
              <div
                v-if="isUploading"
                class="absolute inset-0 bg-white/25 animate-pulse"
              />
            </div>
          </div>

          <!-- 4 阶段进度微步指示器 -->
          <div class="grid grid-cols-4 gap-2 pt-1 border-t border-gray-100 dark:border-zinc-800/70">
            <div
              v-for="st in stages"
              :key="st.id"
              class="flex flex-col items-center text-center space-y-0.5"
            >
              <div class="flex items-center gap-1.5">
                <span
                  class="w-2 h-2 rounded-full transition-all"
                  :class="{
                    'bg-indigo-600 dark:bg-indigo-400 shadow-[0_0_6px_rgba(99,102,241,0.6)]': isStagePassed(st.id) || currentTask.stage === 'completed',
                    'bg-indigo-500 animate-pulse': isStageCurrent(st.id),
                    'bg-gray-300 dark:bg-zinc-700': !isStagePassed(st.id) && !isStageCurrent(st.id) && currentTask.stage !== 'completed',
                  }"
                />
                <span
                  class="text-[11px] font-medium"
                  :class="isStagePassed(st.id) || isStageCurrent(st.id) || currentTask.stage === 'completed' ? 'text-gray-900 dark:text-white font-semibold' : 'text-gray-400 dark:text-zinc-600'"
                >
                  {{ st.name }}
                </span>
              </div>
              <span class="text-[10px] text-gray-400 dark:text-zinc-500 hidden sm:inline">{{ st.desc }}</span>
            </div>
          </div>

          <!-- 底部结果栏：成功状态 -->
          <div
            v-if="currentTask.stage === 'completed'"
            class="pt-2 border-t border-gray-100 dark:border-zinc-800/80 flex items-center justify-between"
          >
            <span class="text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5 font-medium">
              <CheckCircle2 class="w-4 h-4 flex-shrink-0" />
              <span>向量化与多维索引构建完成，已生成 {{ currentTask.chunks }} 个父子切片</span>
            </span>
            <button
              @click="resetUploadState"
              class="px-3 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-gray-50 text-gray-700 dark:text-zinc-200 transition-colors cursor-pointer font-medium"
            >
              继续添加文件
            </button>
          </div>

          <!-- 底部结果栏：失败状态 -->
          <div
            v-else-if="currentTask.stage === 'error'"
            class="pt-2 border-t border-gray-100 dark:border-zinc-800/80 flex items-center justify-between"
          >
            <span class="text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5 font-medium truncate max-w-[75%]">
              <AlertCircle class="w-4 h-4 flex-shrink-0" />
              <span class="truncate">{{ currentTask.errorMessage || '处理失败' }}</span>
            </span>
            <button
              @click="resetUploadState"
              class="px-3 py-1.5 text-xs rounded-lg border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/40 hover:bg-red-100 text-red-700 dark:text-red-300 transition-colors cursor-pointer font-medium"
            >
              返回重新上传
            </button>
          </div>
        </div>

        <!-- 2. 空闲状态下的拖拽选择触发区 -->
        <div
          v-else
          @dragover.prevent
          @drop="handleDrop"
          @click="triggerFileSelect"
          class="border-2 border-dashed border-gray-300 dark:border-zinc-700 hover:border-indigo-400 dark:hover:border-indigo-500 rounded-2xl p-8 text-center cursor-pointer transition-all bg-white/50 dark:bg-zinc-900/30 relative overflow-hidden group"
        >
          <input
            ref="fileInput"
            type="file"
            multiple
            @change="handleFileChange"
            class="hidden"
            accept=".txt,.md,.markdown,.pdf,.docx,.doc,.xlsx,.xls,.xlsm,.csv,.tsv,.json,.py,.js,.ts,.html,.css,.sql,.sh,.log,.yaml,.yml"
          />
          <div>
            <div class="w-12 h-12 rounded-full bg-gray-100 dark:bg-zinc-800 flex items-center justify-center text-gray-700 dark:text-zinc-200 mx-auto mb-3 group-hover:scale-105 group-hover:bg-indigo-50 dark:group-hover:bg-indigo-950/40 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-all">
              <Upload class="w-6 h-6" />
            </div>
            <div class="text-sm font-semibold text-gray-800 dark:text-zinc-200">
              点击选择文件，或将本地文件直接拖拽至此处
            </div>
            <div class="text-xs text-gray-400 mt-1">
              自动进行结构化表格解析、双层父子分块（Parent-Child）并同步构建 Milvus 向量与 BM25 索引
            </div>
            <!-- 格式标签栏 -->
            <div class="flex flex-wrap items-center justify-center gap-1.5 mt-3 pt-3 border-t border-gray-100 dark:border-zinc-800/80">
              <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-red-50 dark:bg-red-950/40 text-red-600 dark:text-red-400 border border-red-200/60 dark:border-red-800/40">PDF 文档</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 border border-blue-200/60 dark:border-blue-800/40">Word (.docx)</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-800/40">Excel (.xlsx)</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 border border-amber-200/60 dark:border-amber-800/40">CSV / TSV</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400 border border-purple-200/60 dark:border-purple-800/40">Markdown (.md)</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-zinc-300 border border-gray-200 dark:border-zinc-700">TXT / 代码文件</span>
            </div>
          </div>
        </div>

        <!-- 已入库集合列表展示 -->
        <div class="space-y-3">
          <h3 class="text-sm font-semibold text-gray-800 dark:text-zinc-200">已入库集合清单</h3>
          
          <div v-if="ragStore.documents.length === 0" class="p-8 text-center border border-gray-200 dark:border-zinc-800 rounded-xl bg-white dark:bg-zinc-900/50 text-gray-400 text-xs">
            暂无已入库文档。点击上方上传区域添加文件以构建专属知识库。
          </div>

          <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div
              v-for="doc in ragStore.documents"
              :key="doc.doc_id"
              class="p-4 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 flex items-center justify-between shadow-sm"
            >
              <div class="flex items-center gap-3 min-w-0">
                <div class="w-9 h-9 rounded-lg bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-zinc-300 flex items-center justify-center flex-shrink-0">
                  <FileCheck class="w-5 h-5" />
                </div>
                <div class="min-w-0">
                  <div class="text-xs font-semibold text-gray-900 dark:text-white truncate">
                    {{ doc.title }}
                  </div>
                  <div class="text-[11px] text-gray-400 font-mono mt-0.5">
                    共 {{ doc.chunks }} 个向量切片 • 类型: {{ doc.doc_type.toUpperCase() }}
                  </div>
                </div>
              </div>

              <!-- 删除按钮 -->
              <button
                @click="handleDeleteDoc(doc.doc_id, doc.title)"
                class="p-1.5 text-gray-400 hover:text-gray-700 dark:hover:text-zinc-200 rounded-md hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
                title="删除此文档的所有切片"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 选项卡 2：录入纯文本表单 -->
      <div v-else-if="activeTab === 'text'" class="space-y-4">
        <div class="bg-white dark:bg-zinc-900 p-5 rounded-2xl border border-gray-200 dark:border-zinc-800 space-y-4">
          <div>
            <label class="block text-xs font-semibold text-gray-700 dark:text-zinc-300 mb-1.5">文档标题 / 标识</label>
            <input
              v-model="textTitle"
              type="text"
              placeholder="例如：Agent 核心设计准则规范"
              class="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent text-xs text-gray-900 dark:text-zinc-100 focus:outline-none focus:border-gray-400 dark:focus:border-zinc-500"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold text-gray-700 dark:text-zinc-300 mb-1.5">正文内容</label>
            <textarea
              v-model="textContent"
              rows="8"
              placeholder="在此处粘贴文本段落、API 规格文档、业务规范或备忘笔记..."
              class="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent text-xs text-gray-900 dark:text-zinc-100 focus:outline-none focus:border-gray-400 dark:focus:border-zinc-500 font-mono"
            ></textarea>
          </div>

          <button
            @click="handleTextSubmit"
            :disabled="!textContent.trim() || isSubmittingText"
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 dark:bg-zinc-600 dark:hover:bg-zinc-500 disabled:opacity-40 text-white font-medium text-xs transition-colors shadow-sm cursor-pointer"
          >
            <Loader2 v-if="isSubmittingText" class="w-4 h-4 animate-spin" />
            <Plus v-else class="w-4 h-4" />
            <span>{{ isSubmittingText ? '正在切分并向量化入库...' : '切分并写入本地向量数据库' }}</span>
          </button>
        </div>
      </div>

      <!-- 选项卡 3：内容检索预览 -->
      <div v-else-if="activeTab === 'search'" class="space-y-4">
        <div class="flex gap-2">
          <input
            v-model="searchQuery"
            @keydown.enter="handleSearch"
            type="text"
            placeholder="输入关键词或问题，快速预览知识库中匹配的内容段落..."
            class="flex-1 px-4 py-2.5 rounded-xl border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-xs text-gray-900 dark:text-zinc-100 focus:outline-none focus:border-gray-400 dark:focus:border-zinc-500"
          />
          <button
            @click="handleSearch"
            :disabled="!searchQuery.trim() || isSearching"
            class="px-5 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 dark:bg-zinc-600 dark:hover:bg-zinc-500 text-white text-xs font-semibold flex items-center gap-2 shadow-sm transition-colors cursor-pointer"
          >
            <Search class="w-4 h-4" />
            <span>快速检索</span>
          </button>
        </div>

        <!-- 检索结果列表展示 -->
        <div class="space-y-3">
          <div v-if="ragStore.searchResults.length === 0 && searchQuery" class="p-8 text-center border border-gray-200 dark:border-zinc-800 rounded-2xl bg-white/40 dark:bg-zinc-900/40 text-gray-400 text-xs">
            未在知识库中找到与该关键词相关的参考内容。
          </div>

          <div
            v-for="(r, idx) in ragStore.searchResults"
            :key="idx"
            class="p-4 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 space-y-2 shadow-sm"
          >
            <div class="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-zinc-200">
              <span class="flex items-center gap-1.5 min-w-0 truncate">
                <FileText class="w-3.5 h-3.5 flex-shrink-0" />
                <span class="truncate">参考文档: 《{{ r.title }}》</span>
              </span>
              <div class="flex items-center gap-2 flex-shrink-0 font-mono text-[11px]">
                <span v-if="r.distance !== undefined" class="px-2 py-0.5 rounded bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-zinc-400">
                  距离: {{ r.distance }}
                </span>
                <span class="text-gray-400">
                  段落 #{{ r.chunk_index !== undefined ? r.chunk_index + 1 : idx + 1 }}
                </span>
              </div>
            </div>
            <div class="text-xs text-gray-700 dark:text-zinc-300 bg-gray-50 dark:bg-zinc-950/60 p-3 rounded-lg leading-relaxed whitespace-pre-wrap select-text">
              {{ r.content }}
            </div>
          </div>
        </div>
      </div>

      <!-- 选项卡 4：灾备快照（方案 C） -->
      <div v-else-if="activeTab === 'backup'" class="space-y-4">
        <div class="p-5 rounded-2xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 space-y-4 shadow-sm">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-gray-800 dark:text-zinc-200 flex items-center gap-2">
              <ShieldCheck class="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              方案 C · 全自动双写灾备
            </h3>
            <button
              @click="ragStore.fetchBackupStatus"
              class="text-xs text-gray-500 hover:text-gray-800 dark:hover:text-zinc-200 flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw class="w-3.5 h-3.5" />
              刷新状态
            </button>
          </div>

          <div v-if="ragStore.backupStatus" class="space-y-3 text-xs">
            <div class="flex items-center justify-between py-2 border-b border-gray-100 dark:border-zinc-800">
              <span class="text-gray-500 dark:text-zinc-400">快照内文档数</span>
              <span class="font-semibold text-gray-800 dark:text-zinc-200">{{ ragStore.backupStatus.backup_docs_count }} 篇</span>
            </div>
            <div class="flex items-center justify-between py-2 border-b border-gray-100 dark:border-zinc-800">
              <span class="text-gray-500 dark:text-zinc-400">最近快照时间</span>
              <span class="font-semibold text-gray-800 dark:text-zinc-200">{{ formatBackupTime(ragStore.backupStatus.updated_at) }}</span>
            </div>
            <div class="space-y-2">
              <div class="flex items-center justify-between gap-3">
                <span class="text-gray-500 dark:text-zinc-400 flex-shrink-0">主快照</span>
                <span
                  class="px-2 py-0.5 rounded text-[11px] font-medium flex-shrink-0"
                  :class="ragStore.backupStatus.primary_backup_exists ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400' : 'bg-red-50 dark:bg-red-950/40 text-red-600 dark:text-red-400'"
                >
                  {{ ragStore.backupStatus.primary_backup_exists ? '已就绪' : '缺失' }}
                </span>
              </div>
              <div class="font-mono text-[10px] text-gray-400 dark:text-zinc-500 break-all select-text">{{ ragStore.backupStatus.primary_backup_path }}</div>
              <div class="flex items-center justify-between gap-3">
                <span class="text-gray-500 dark:text-zinc-400 flex-shrink-0">冗余快照（系统级）</span>
                <span
                  class="px-2 py-0.5 rounded text-[11px] font-medium flex-shrink-0"
                  :class="ragStore.backupStatus.redundant_backup_exists ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400' : 'bg-red-50 dark:bg-red-950/40 text-red-600 dark:text-red-400'"
                >
                  {{ ragStore.backupStatus.redundant_backup_exists ? '已就绪' : '缺失' }}
                </span>
              </div>
              <div class="font-mono text-[10px] text-gray-400 dark:text-zinc-500 break-all select-text">{{ ragStore.backupStatus.redundant_backup_path }}</div>
            </div>
          </div>
          <div v-else class="text-xs text-gray-400 dark:text-zinc-500 flex items-center gap-1.5">
            <AlertCircle class="w-3.5 h-3.5" />
            暂未获取到灾备状态，请点击右上角刷新。
          </div>

          <div class="flex items-center gap-2.5 pt-2 border-t border-gray-100 dark:border-zinc-800">
            <button
              @click="handleRestoreBackup"
              :disabled="isRestoring || isExporting"
              class="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-800 text-xs font-medium text-gray-700 dark:text-zinc-300 transition-colors disabled:opacity-50 cursor-pointer"
            >
              <RotateCcw class="w-3.5 h-3.5" :class="{ 'animate-spin': isRestoring }" />
              <span>从快照恢复</span>
            </button>
            <button
              @click="handleExportBackup"
              :disabled="isRestoring || isExporting"
              class="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 dark:bg-zinc-600 dark:hover:bg-zinc-500 text-white text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer"
            >
              <Download class="w-3.5 h-3.5" :class="{ 'animate-bounce': isExporting }" />
              <span>导出灾备包</span>
            </button>
          </div>

          <p class="text-[11px] text-gray-400 dark:text-zinc-500 leading-relaxed">
            每次写入知识库时会自动双写主/冗余两份快照；若向量库数据被误删或损坏，系统启动时将自动从快照自愈重建，也可在此手动恢复或导出留存。
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
