<script setup lang="ts">
/**
 * 本地知识库 (RAG) 管理视图
 * 具备拖拽多格式文件解析入库、直接录入文本笔记、集合列表浏览与删除、以及语义相似度检索测试台。
 */
import { ref, onMounted } from 'vue'
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
} from 'lucide-vue-next'
import { useRagStore } from '../stores/rag'

const message = useMessage()
const ragStore = useRagStore()

// 当前激活的选项卡：'files' 文件集合 | 'text' 录入文本 | 'search' 检索测试
const activeTab = ref<'files' | 'text' | 'search'>('files')
// 文件输入框 DOM 引用
const fileInput = ref<HTMLInputElement | null>(null)
// 录入文本表单数据
const textTitle = ref('')
const textContent = ref('')
// 检索测试关键词与加载状态
const searchQuery = ref('')
const isSearching = ref(false)

onMounted(() => {
  ragStore.fetchDocuments()
})

// 触发隐藏的系统原生文件选择器
const triggerFileSelect = () => {
  fileInput.value?.click()
}

// 处理点击选择上传的文件
const handleFileChange = async (e: Event) => {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    const file = target.files[0]
    const loadingMsg = message.loading(`正在解析并向量化《${file.name}》...`, { duration: 0 })
    try {
      const res = await ragStore.uploadFile(file)
      if (res.success) {
        message.success(res.message, { duration: 4000 })
      } else {
        message.error(res.message, { duration: 6000 })
      }
    } finally {
      loadingMsg.destroy()
      target.value = ''
    }
  }
}

// 处理拖拽放入文件
const handleDrop = async (e: DragEvent) => {
  e.preventDefault()
  if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
    const file = e.dataTransfer.files[0]
    const loadingMsg = message.loading(`正在解析并向量化《${file.name}》...`, { duration: 0 })
    try {
      const res = await ragStore.uploadFile(file)
      if (res.success) {
        message.success(res.message, { duration: 4000 })
      } else {
        message.error(res.message, { duration: 6000 })
      }
    } finally {
      loadingMsg.destroy()
    }
  }
}

// 提交录入的纯文本/Markdown 笔记
const handleTextSubmit = async () => {
  if (!textContent.value.trim()) {
    message.warning('请输入笔记正文内容')
    return
  }
  const loadingMsg = message.loading('正在切分并存入知识库...', { duration: 0 })
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
    loadingMsg.destroy()
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
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-gray-50 text-xs font-medium text-gray-700 dark:text-zinc-300 transition-colors"
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
          class="pb-2 px-3 font-semibold transition-colors border-b-2"
          :class="[activeTab === 'files' ? 'border-gray-900 dark:border-zinc-100 text-gray-900 dark:text-zinc-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-zinc-300']"
        >
          已存文档 ({{ ragStore.documents.length }})
        </button>
        <button
          @click="activeTab = 'text'"
          class="pb-2 px-3 font-semibold transition-colors border-b-2"
          :class="[activeTab === 'text' ? 'border-gray-900 dark:border-zinc-100 text-gray-900 dark:text-zinc-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-zinc-300']"
        >
          添加笔记与纯文本
        </button>
        <button
          @click="activeTab = 'search'"
          class="pb-2 px-3 font-semibold transition-colors border-b-2"
          :class="[activeTab === 'search' ? 'border-gray-900 dark:border-zinc-100 text-gray-900 dark:text-zinc-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-zinc-300']"
        >
          内容检索预览
        </button>
      </div>

      <!-- 选项卡 1：文档管理与拖拽上传 -->
      <div v-if="activeTab === 'files'" class="space-y-6">
        <!-- 拖拽上传文件触发区 -->
        <div
          @dragover.prevent
          @drop="handleDrop"
          @click="!ragStore.isLoading && triggerFileSelect()"
          class="border-2 border-dashed border-gray-300 dark:border-zinc-700 hover:border-gray-400 dark:hover:border-zinc-500 rounded-2xl p-8 text-center cursor-pointer transition-all bg-white/50 dark:bg-zinc-900/30 relative overflow-hidden group"
          :class="{ 'opacity-70 cursor-not-allowed': ragStore.isLoading }"
        >
          <input
            ref="fileInput"
            type="file"
            @change="handleFileChange"
            class="hidden"
            accept=".txt,.md,.markdown,.pdf,.docx,.doc,.xlsx,.xls,.xlsm,.csv,.tsv,.json,.py,.js,.ts,.html,.css,.sql,.sh,.log,.yaml,.yml"
          />
          <div v-if="ragStore.isLoading" class="flex flex-col items-center justify-center py-4">
            <Loader2 class="w-8 h-8 text-indigo-600 dark:text-indigo-400 animate-spin mb-2" />
            <div class="text-xs font-semibold text-gray-800 dark:text-zinc-200">正在解析并切分向量入库...</div>
            <div class="text-[11px] text-gray-400 mt-0.5">自动执行表格提取、双层父子分块（Parent-Child）与多维索引</div>
          </div>
          <div v-else>
            <div class="w-12 h-12 rounded-full bg-gray-100 dark:bg-zinc-800 flex items-center justify-center text-gray-700 dark:text-zinc-200 mx-auto mb-3 group-hover:scale-105 transition-transform">
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
            :disabled="!textContent.trim() || ragStore.isLoading"
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 dark:bg-zinc-600 dark:hover:bg-zinc-500 disabled:opacity-40 text-white font-medium text-xs transition-colors shadow-sm"
          >
            <Plus class="w-4 h-4" />
            <span>切分并写入本地向量数据库</span>
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
            class="px-5 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 dark:bg-zinc-600 dark:hover:bg-zinc-500 text-white text-xs font-semibold flex items-center gap-2 shadow-sm transition-colors"
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
    </div>
  </div>
</template>
