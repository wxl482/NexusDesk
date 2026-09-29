<script setup lang="ts">
/**
 * 智能体技能与扩展能力中心 (ToolsView)
 * 分类清晰、紧凑精致地展示智能助手内置的超能力，并原生支持 Anthropic Model Context Protocol (MCP) 外部服务生态管理。
 */
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import {
  Terminal,
  FolderSync,
  Globe,
  BookOpen,
  Calculator,
  RefreshCw,
  Cpu,
  Boxes,
  Plus,
  Trash2,
  Play,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Code,
  Sliders,
} from 'lucide-vue-next'
import { apiClient } from '../api/client'

const message = useMessage()

// 当前激活选项卡：'native' 系统内置工具 | 'mcp' MCP 外部插件生态
const activeTab = ref<'native' | 'mcp'>('native')

interface SkillItem {
  id: string
  name: string
  icon: any
  description: string
  exampleQuery: string
}

interface SkillCategory {
  id: string
  title: string
  icon: any
  skills: SkillItem[]
}

const skillCategories = ref<SkillCategory[]>([
  {
    id: 'system',
    title: '系统操控与开发环境',
    icon: Cpu,
    skills: [
      {
        id: 'terminal',
        name: '终端 Shell 执行',
        icon: Terminal,
        description: '在安全受控的环境中执行终端指令，支持自动化编译、构建与 Git 状态监测。',
        exampleQuery: '执行 git status 查看最新改动',
      },
      {
        id: 'file',
        name: '本地文件系统管理',
        icon: FolderSync,
        description: '读取、编辑与保存代码文件，支持目录树层级扫描与递归新建。',
        exampleQuery: '读取 package.json 依赖项',
      },
    ],
  },
  {
    id: 'knowledge',
    title: '信息检索与专属知识',
    icon: Globe,
    skills: [
      {
        id: 'search',
        name: '实时互联网检索',
        icon: Globe,
        description: '连接公开网络查询最新技术文档、官方新闻资讯与实时权威事实。',
        exampleQuery: '搜索 DeepSeek 最新模型动态',
      },
      {
        id: 'rag',
        name: '私有知识库检索',
        icon: BookOpen,
        description: '基于 Milvus 向量库与 BM25 混合检索，提供精准严谨的溯源问答。',
        exampleQuery: '查阅知识库中的核心设计指南',
      },
    ],
  },
  {
    id: 'analysis',
    title: '分析引擎与数据计算',
    icon: Calculator,
    skills: [
      {
        id: 'math',
        name: '高精度数据计算',
        icon: Calculator,
        description: '具备高精度数学逻辑求解与业务数据统计分析能力，运算结果真实确凿。',
        exampleQuery: '计算年复合增长率与趋势预测',
      },
    ],
  },
])

// MCP 服务接口定义
interface MCPServer {
  id: string
  name: string
  transport: string
  command: string
  args: string[]
  env?: Record<string, string>
  enabled: boolean
  description?: string
  tools?: any[]
  tools_count?: number
}

const mcpServers = ref<MCPServer[]>([])
const isLoading = ref(false)
const probingId = ref<string | null>(null)
const expandedServerId = ref<string | null>(null)

// 注册弹窗控制与表单
const showAddModal = ref(false)
const newServer = ref({
  id: '',
  name: '',
  command: '',
  argsText: '',
  description: '',
  enabled: true,
})

// MCP 常用开箱即用官方预设模板
const presets = [
  {
    label: '官方 Fetch 爬虫',
    id: 'fetch',
    name: 'Web Content Fetcher',
    command: 'python3',
    argsText: '-m mcp.server.fastmcp',
    description: 'Anthropic 官方网页内容与 Markdown 提取服务',
  },
  {
    label: '本地 SQLite 数据库',
    id: 'sqlite',
    name: 'SQLite Database Query',
    command: 'npx',
    argsText: '-y @modelcontextprotocol/server-sqlite --db-path ./backend/data/app.db',
    description: '通过标准 SQL 查询本地 SQLite 数据库表结构与数据记录',
  },
  {
    label: '安全本地文件系统',
    id: 'filesystem',
    name: 'Secure Filesystem Access',
    command: 'npx',
    argsText: '-y @modelcontextprotocol/server-filesystem ./backend/data/workspace',
    description: '限定在工作区安全目录下的文件读写与搜索服务',
  },
  {
    label: 'GitHub 官方服务',
    id: 'github',
    name: 'GitHub API Service',
    command: 'npx',
    argsText: '-y @modelcontextprotocol/server-github',
    description: '管理 GitHub 仓库、提交、Issues 与 Pull Requests',
  },
]

const applyPreset = (p: typeof presets[0]) => {
  newServer.value.id = p.id
  newServer.value.name = p.name
  newServer.value.command = p.command
  newServer.value.argsText = p.argsText
  newServer.value.description = p.description
}

const fetchMcpServers = async () => {
  isLoading.value = true
  try {
    const servers = await apiClient.getMcpServers()
    mcpServers.value = servers || []
  } catch (err: any) {
    console.error('获取 MCP 服务列表失败:', err)
  } finally {
    isLoading.value = false
  }
}

const handleToggleMcp = async (server: MCPServer) => {
  const newStatus = !server.enabled
  try {
    await apiClient.toggleMcpServer(server.id, newStatus)
    server.enabled = newStatus
    message.success(`已${newStatus ? '启用' : '禁用'} MCP 服务《${server.name}》`)
  } catch (err: any) {
    message.error(`切换状态失败: ${err.message}`)
  }
}

const handleProbeMcp = async (server: MCPServer) => {
  probingId.value = server.id
  try {
    const res = await apiClient.probeMcpServer(server.id)
    server.tools = res.tools || []
    server.tools_count = (res.tools || []).length
    expandedServerId.value = server.id
    if ((server.tools_count ?? 0) > 0) {
      message.success(`握手成功！服务《${server.name}》成功探测到 ${server.tools_count} 个可用工具`)
    } else {
      message.warning(`服务《${server.name}》连接完成，但未返回可用工具。`)
    }
  } catch (err: any) {
    message.error(`探测失败: ${err.response?.data?.detail || err.message}`)
  } finally {
    probingId.value = null
  }
}

const handleDeleteMcp = async (serverId: string, serverName: string) => {
  try {
    await apiClient.deleteMcpServer(serverId)
    mcpServers.value = mcpServers.value.filter(s => s.id !== serverId)
    message.success(`已移除 MCP 服务《${serverName}》`)
  } catch (err: any) {
    message.error(`删除失败: ${err.message}`)
  }
}

const handleCreateMcp = async () => {
  if (!newServer.value.id.trim() || !newServer.value.command.trim()) {
    message.warning('请填写服务唯一标识与启动命令')
    return
  }
  const args = newServer.value.argsText
    .trim()
    .split(/\s+/)
    .filter(a => a.length > 0)

  try {
    await apiClient.registerMcpServer({
      id: newServer.value.id.trim(),
      name: newServer.value.name.trim() || newServer.value.id.trim(),
      command: newServer.value.command.trim(),
      args,
      enabled: newServer.value.enabled,
      description: newServer.value.description.trim(),
    })
    message.success(`MCP 服务《${newServer.value.name}》注册成功！`)
    showAddModal.value = false
    newServer.value = { id: '', name: '', command: '', argsText: '', description: '', enabled: true }
    await fetchMcpServers()
  } catch (err: any) {
    message.error(`注册失败: ${err.response?.data?.detail || err.message}`)
  }
}

const handleRefresh = async () => {
  if (activeTab.value === 'mcp') {
    await fetchMcpServers()
  } else {
    isLoading.value = true
    try {
      await apiClient.getTools()
    } finally {
      isLoading.value = false
    }
  }
}

onMounted(() => {
  fetchMcpServers()
})
</script>

<template>
  <div class="flex-1 flex flex-col h-full bg-gray-50/50 dark:bg-zinc-950 p-6 overflow-y-auto">
    <div class="max-w-5xl mx-auto w-full space-y-6">
      <!-- 页面顶部标题 (支持无边框窗口拖拽) -->
      <div class="flex items-center justify-between pb-4 border-b border-gray-200 dark:border-zinc-800 window-drag-region select-none">
        <div class="window-no-drag">
          <h1 class="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            技能与扩展中心
          </h1>
          <p class="text-xs text-gray-500 dark:text-zinc-400 mt-1">
            管理智能体原生执行工具，以及基于 Anthropic MCP (Model Context Protocol) 的外部生态插件。
          </p>
        </div>

        <div class="flex items-center gap-2.5 window-no-drag">
          <button
            v-if="activeTab === 'mcp'"
            @click="showAddModal = true"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-900 hover:bg-black dark:bg-zinc-100 dark:hover:bg-white text-white dark:text-zinc-900 text-xs font-medium transition-colors shadow-2xs cursor-pointer"
          >
            <Plus class="w-3.5 h-3.5" />
            <span>注册 MCP 服务</span>
          </button>

          <button
            @click="handleRefresh"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-800 text-xs font-medium text-gray-700 dark:text-zinc-300 transition-colors shadow-2xs cursor-pointer"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': isLoading }" />
            <span>刷新</span>
          </button>
        </div>
      </div>

      <!-- 选项卡切换 -->
      <div class="flex items-center gap-2 border-b border-gray-200 dark:border-zinc-800 text-xs">
        <button
          @click="activeTab = 'native'"
          class="pb-2 px-3 font-semibold transition-colors border-b-2 flex items-center gap-1.5"
          :class="[activeTab === 'native' ? 'border-gray-900 dark:border-zinc-100 text-gray-900 dark:text-zinc-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-zinc-300']"
        >
          <Cpu class="w-3.5 h-3.5" />
          <span>内置核心技能</span>
        </button>
        <button
          @click="activeTab = 'mcp'"
          class="pb-2 px-3 font-semibold transition-colors border-b-2 flex items-center gap-1.5"
          :class="[activeTab === 'mcp' ? 'border-gray-900 dark:border-zinc-100 text-gray-900 dark:text-zinc-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-zinc-300']"
        >
          <Boxes class="w-3.5 h-3.5 text-indigo-500" />
          <span>MCP 外部协议生态 ({{ mcpServers.length }})</span>
        </button>
      </div>

      <!-- 选项卡 1：内置原生技能 -->
      <div v-if="activeTab === 'native'" class="space-y-6">
        <div
          v-for="cat in skillCategories"
          :key="cat.id"
          class="space-y-3"
        >
          <!-- 分类标题行 -->
          <div class="flex items-center gap-2 text-xs font-semibold text-gray-600 dark:text-zinc-400 px-1">
            <component :is="cat.icon" class="w-3.5 h-3.5 text-gray-500 dark:text-zinc-400" />
            <span>{{ cat.title }}</span>
            <span class="text-[11px] font-normal text-gray-400">({{ cat.skills.length }})</span>
          </div>

          <!-- 紧凑技能卡片网格 -->
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <div
              v-for="s in cat.skills"
              :key="s.id"
              class="p-3.5 rounded-xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:border-gray-300 dark:hover:border-zinc-600 transition-all flex flex-col justify-between shadow-2xs group"
            >
              <div class="space-y-2">
                <!-- 头部：小图标 + 技能名 + 状态指示 -->
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2.5 min-w-0">
                    <div class="w-7 h-7 rounded-lg bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-zinc-300 flex items-center justify-center flex-shrink-0 border border-gray-200/70 dark:border-zinc-700/60">
                      <component :is="s.icon" class="w-4 h-4" />
                    </div>
                    <h3 class="text-xs font-semibold text-gray-900 dark:text-white truncate">
                      {{ s.name }}
                    </h3>
                  </div>

                  <span class="flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400 font-medium flex-shrink-0">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_4px_rgba(16,185,129,0.5)]"></span>
                    <span>就绪</span>
                  </span>
                </div>

                <!-- 描述 -->
                <p class="text-[11px] text-gray-500 dark:text-zinc-400 leading-relaxed line-clamp-2">
                  {{ s.description }}
                </p>
              </div>

              <!-- 底部提问场景示例 -->
              <div class="mt-2.5 pt-2 border-t border-gray-100 dark:border-zinc-800/60 flex items-center gap-1.5 text-[10px] text-gray-400 dark:text-zinc-500 truncate">
                <span class="font-medium text-gray-500 dark:text-zinc-400 flex-shrink-0">示例:</span>
                <span class="italic truncate group-hover:text-gray-900 dark:group-hover:text-zinc-100 transition-colors">
                  “{{ s.exampleQuery }}”
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 选项卡 2：MCP 外部插件协议 -->
      <div v-else-if="activeTab === 'mcp'" class="space-y-4">
        <!-- MCP 服务列表 -->
        <div v-if="mcpServers.length === 0" class="p-8 text-center border border-gray-200 dark:border-zinc-800 rounded-xl bg-white dark:bg-zinc-900/50 text-gray-400 text-xs">
          暂无已配置的 MCP 服务。点击右上角「注册 MCP 服务」快速绑定官方或社区插件。
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="s in mcpServers"
            :key="s.id"
            class="rounded-xl border border-gray-200/90 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden shadow-2xs transition-all"
          >
            <div class="p-4 flex items-center justify-between gap-4">
              <!-- 左侧信息 -->
              <div class="flex items-center gap-3 min-w-0">
                <div class="w-9 h-9 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center flex-shrink-0 border border-indigo-200/50 dark:border-indigo-800/40">
                  <Boxes class="w-5 h-5" />
                </div>
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <h3 class="text-xs font-bold text-gray-900 dark:text-white truncate">
                      {{ s.name }}
                    </h3>
                    <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-100 dark:bg-zinc-800 text-gray-500">
                      ID: {{ s.id }}
                    </span>
                    <span
                      class="text-[10px] px-1.5 py-0.5 rounded font-medium"
                      :class="s.enabled ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400' : 'bg-gray-100 dark:bg-zinc-800 text-gray-400'"
                    >
                      {{ s.enabled ? '已启用' : '已停用' }}
                    </span>
                  </div>
                  <div class="text-[11px] text-gray-500 dark:text-zinc-400 mt-1 line-clamp-1">
                    {{ s.description || '无附加描述' }}
                  </div>
                  <div class="text-[10px] font-mono text-gray-400 mt-1 flex items-center gap-1.5">
                    <span class="text-gray-500">命令:</span>
                    <span class="bg-gray-50 dark:bg-zinc-800/80 px-1 rounded">{{ s.command }} {{ s.args.join(' ') }}</span>
                  </div>
                </div>
              </div>

              <!-- 右侧操作 -->
              <div class="flex items-center gap-2 flex-shrink-0">
                <!-- 探测工具按钮 -->
                <button
                  @click="handleProbeMcp(s)"
                  :disabled="probingId === s.id || !s.enabled"
                  class="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-gray-50 text-xs font-medium text-gray-700 dark:text-zinc-200 disabled:opacity-50 transition-colors cursor-pointer"
                  title="通过 stdio 连接并探测此服务提供的工具"
                >
                  <Play class="w-3.5 h-3.5 text-indigo-500" :class="{ 'animate-spin': probingId === s.id }" />
                  <span>{{ probingId === s.id ? '握手中...' : '探测工具' }}</span>
                </button>

                <!-- 展开已探测工具 -->
                <button
                  v-if="s.tools && s.tools.length > 0"
                  @click="expandedServerId = expandedServerId === s.id ? null : s.id"
                  class="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 transition-colors cursor-pointer"
                >
                  <span>{{ s.tools.length }} 个工具</span>
                  <component :is="expandedServerId === s.id ? ChevronDown : ChevronRight" class="w-3.5 h-3.5" />
                </button>

                <!-- 切换开关 -->
                <button
                  @click="handleToggleMcp(s)"
                  class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
                  :class="s.enabled ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-zinc-700'"
                >
                  <span
                    class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                    :class="s.enabled ? 'translate-x-4' : 'translate-x-0'"
                  />
                </button>

                <!-- 删除按钮 -->
                <button
                  @click="handleDeleteMcp(s.id, s.name)"
                  class="p-1.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
                  title="删除该 MCP 服务"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </div>

            <!-- 展开的工具列表 -->
            <div
              v-if="expandedServerId === s.id && s.tools && s.tools.length > 0"
              class="border-t border-gray-100 dark:border-zinc-800 bg-gray-50/50 dark:bg-zinc-950/30 p-3 space-y-2"
            >
              <div class="text-[11px] font-semibold text-gray-600 dark:text-zinc-400 px-1">
                已装配到 Agent 工具链的 MCP Tools:
              </div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div
                  v-for="tool in s.tools"
                  :key="tool.name"
                  class="p-2.5 rounded-lg border border-gray-200/80 dark:border-zinc-800 bg-white dark:bg-zinc-900 space-y-1"
                >
                  <div class="flex items-center gap-1.5">
                    <Code class="w-3.5 h-3.5 text-indigo-500" />
                    <span class="text-xs font-semibold text-gray-900 dark:text-white font-mono">
                      mcp_{{ s.id }}_{{ tool.name }}
                    </span>
                  </div>
                  <div class="text-[11px] text-gray-500 dark:text-zinc-400 line-clamp-2">
                    {{ tool.description || '无详细描述' }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 注册 MCP 外部服务模态弹窗 -->
    <div
      v-if="showAddModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
    >
      <div class="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-4">
        <div class="flex items-center justify-between pb-3 border-b border-gray-100 dark:border-zinc-800">
          <div class="flex items-center gap-2">
            <Boxes class="w-5 h-5 text-indigo-500" />
            <h2 class="text-sm font-bold text-gray-900 dark:text-white">注册外部 MCP 服务</h2>
          </div>
          <button
            @click="showAddModal = false"
            class="text-gray-400 hover:text-gray-600 dark:hover:text-zinc-200 cursor-pointer"
          >
            ✕
          </button>
        </div>

        <!-- 常用预设快捷填入 -->
        <div>
          <label class="block text-[11px] font-semibold text-gray-500 dark:text-zinc-400 mb-1.5">
            一键载入官方预设模板:
          </label>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="p in presets"
              :key="p.id"
              @click="applyPreset(p)"
              class="px-2 py-1 rounded text-[11px] font-medium border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 hover:bg-indigo-50 hover:text-indigo-600 dark:hover:bg-indigo-950/40 dark:hover:text-indigo-300 transition-colors cursor-pointer"
            >
              {{ p.label }}
            </button>
          </div>
        </div>

        <!-- 表单 -->
        <div class="space-y-3 text-xs">
          <div>
            <label class="block font-medium text-gray-700 dark:text-zinc-300 mb-1">服务唯一标识符 (ID)</label>
            <input
              v-model="newServer.id"
              type="text"
              placeholder="例如：sqlite 或 github"
              class="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent text-gray-900 dark:text-zinc-100 font-mono text-xs focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div>
            <label class="block font-medium text-gray-700 dark:text-zinc-300 mb-1">展示名称</label>
            <input
              v-model="newServer.name"
              type="text"
              placeholder="例如：SQLite 本地数据库查询"
              class="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent text-gray-900 dark:text-zinc-100 text-xs focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div class="grid grid-cols-3 gap-2">
            <div>
              <label class="block font-medium text-gray-700 dark:text-zinc-300 mb-1">启动命令</label>
              <input
                v-model="newServer.command"
                type="text"
                placeholder="npx 或 python3"
                class="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent text-gray-900 dark:text-zinc-100 font-mono text-xs focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div class="col-span-2">
              <label class="block font-medium text-gray-700 dark:text-zinc-300 mb-1">命令参数 (空格分隔)</label>
              <input
                v-model="newServer.argsText"
                type="text"
                placeholder="-y @modelcontextprotocol/server-xxx"
                class="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent text-gray-900 dark:text-zinc-100 font-mono text-xs focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          <div>
            <label class="block font-medium text-gray-700 dark:text-zinc-300 mb-1">服务描述</label>
            <input
              v-model="newServer.description"
              type="text"
              placeholder="简述该服务提供的能力..."
              class="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent text-gray-900 dark:text-zinc-100 text-xs focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        <!-- 底部按钮 -->
        <div class="flex items-center justify-end gap-2 pt-3 border-t border-gray-100 dark:border-zinc-800">
          <button
            @click="showAddModal = false"
            class="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 text-xs text-gray-600 dark:text-zinc-300 hover:bg-gray-50 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
          >
            取消
          </button>
          <button
            @click="handleCreateMcp"
            class="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer"
          >
            保存并注册
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
