<script setup lang="ts">
/**
 * NexusDesk 可视化节点编排工作流画布 (Workflow Canvas)
 * 对标 Dify / ComfyUI 风格：
 * 1. 点阵网格无限画布，支持节点自由拖拽定位；
 * 2. 平滑 SVG 贝塞尔曲线动态连线与流光运行动画；
 * 3. 涵盖定时器、网页抓取、知识库提炼、AI周报生成、飞书Webhook通知全工种节点；
 * 4. 内置金标准自动化周报编排模版，支持单次全链路调试运行与周期性后台调度。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import {
  Clock,
  Globe,
  BookOpen,
  Sparkles,
  Send,
  Mail,
  Play,
  RotateCcw,
  Plus,
  Trash2,
  Save,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  ExternalLink,
  Copy,
  ChevronRight,
  Settings2,
  Layers,
  ArrowRight,
} from 'lucide-vue-next'
import { apiClient } from '../api/client'

const message = useMessage()

// 节点数据类型定义
interface WorkflowNode {
  id: string
  type: 'timer' | 'crawler' | 'rag' | 'llm' | 'feishu' | 'email'
  title: string
  x: number
  y: number
  config: Record<string, any>
  status?: 'idle' | 'running' | 'completed' | 'error'
  output?: any
  error?: string
}

interface WorkflowEdge {
  id: string
  source: string
  target: string
  source_handle?: string
  target_handle?: string
}

interface WorkflowItem {
  id: string
  name: string
  description?: string
  cron?: string
  is_scheduled?: boolean
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
}

// 当前工作流数据
const workflow = ref<WorkflowItem>({
  id: 'tpl_weekly_report_feishu',
  name: '定时行业动态抓取 ➜ 知识库提炼 ➜ AI周报 ➜ 飞书推送',
  description: '每周五定时自动化抓取最新前沿资讯，结合本地企业知识库背景，由大模型深度合成结构化精美周报并实时推送至飞书大群。',
  cron: '0 18 * * 5',
  is_scheduled: false,
  nodes: [],
  edges: [],
})

// 可用工作流列表
const workflowList = ref<WorkflowItem[]>([])
const selectedNodeId = ref<string | null>(null)

// 画布视图状态（平移与交互）
const canvasRef = ref<HTMLDivElement | null>(null)
const isDraggingNode = ref(false)
const draggedNodeId = ref<string | null>(null)
const dragOffset = ref({ x: 0, y: 0 })

// 连线创建状态
const connectingSourceId = ref<string | null>(null)
const mousePos = ref({ x: 0, y: 0 })

// 执行状态与日志抽屉
const isRunning = ref(false)
const isSaving = ref(false)
const showResultDrawer = ref(false)
const executionResults = ref<any>(null)
const executionLogs = ref<any[]>([])

// 节点卡片尺寸常量 (用于计算端口坐标)
const NODE_WIDTH = 260
const NODE_HEIGHT = 135

// 节点元数据配置
const NODE_TYPES: Record<string, { label: string; icon: any; color: string; bg: string; border: string; desc: string }> = {
  timer: {
    label: '定时调度器',
    icon: Clock,
    color: 'text-amber-500',
    bg: 'bg-amber-50 dark:bg-amber-950/40',
    border: 'border-amber-300 dark:border-amber-700',
    desc: '按 Cron 或周/日周期驱动任务',
  },
  crawler: {
    label: '网页抓取与萃取',
    icon: Globe,
    color: 'text-blue-500',
    bg: 'bg-blue-50 dark:bg-blue-950/40',
    border: 'border-blue-300 dark:border-blue-700',
    desc: '抓取目标 URL 并清洗正文',
  },
  rag: {
    label: '知识库语义提炼',
    icon: BookOpen,
    color: 'text-purple-500',
    bg: 'bg-purple-50 dark:bg-purple-950/40',
    border: 'border-purple-300 dark:border-purple-700',
    desc: '双路混合检索召回私有依据',
  },
  llm: {
    label: 'AI 深度合成周报',
    icon: Sparkles,
    color: 'text-emerald-500',
    bg: 'bg-emerald-50 dark:bg-emerald-950/40',
    border: 'border-emerald-300 dark:border-emerald-700',
    desc: '大模型根据输入聚合撰写报告',
  },
  feishu: {
    label: '飞书群机器人通知',
    icon: Send,
    color: 'text-rose-500',
    bg: 'bg-rose-50 dark:bg-rose-950/40',
    border: 'border-rose-300 dark:border-rose-700',
    desc: '将交付产物推送至飞书群聊',
  },
  email: {
    label: '邮件发送通知',
    icon: Mail,
    color: 'text-indigo-500',
    bg: 'bg-indigo-50 dark:bg-indigo-950/40',
    border: 'border-indigo-300 dark:border-indigo-700',
    desc: 'SMTP 邮件投递与抄送',
  },
}

// 当前选中的节点对象
const selectedNode = computed(() => {
  return workflow.value.nodes.find(n => n.id === selectedNodeId.value) || null
})

// 获取节点的输入与输出端口坐标
const getNodePortCoords = (node: WorkflowNode) => {
  return {
    input: { x: node.x, y: node.y + NODE_HEIGHT / 2 },
    output: { x: node.x + NODE_WIDTH, y: node.y + NODE_HEIGHT / 2 },
  }
}

// 计算贝塞尔连线路径
const calculateBezierPath = (x1: number, y1: number, x2: number, y2: number) => {
  const dx = Math.max(Math.abs(x2 - x1) * 0.5, 40)
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

// 连线列表的实际渲染数据
interface RenderedEdge {
  id: string
  source: string
  target: string
  path: string
  midX: number
  midY: number
  isRunning: boolean
}

const renderedEdges = computed<RenderedEdge[]>(() => {
  const result: RenderedEdge[] = []
  for (const edge of workflow.value.edges) {
    const srcNode = workflow.value.nodes.find(n => n.id === edge.source)
    const tgtNode = workflow.value.nodes.find(n => n.id === edge.target)
    if (!srcNode || !tgtNode) continue

    const srcCoord = getNodePortCoords(srcNode).output
    const tgtCoord = getNodePortCoords(tgtNode).input
    const path = calculateBezierPath(srcCoord.x, srcCoord.y, tgtCoord.x, tgtCoord.y)
    const midX = (srcCoord.x + tgtCoord.x) / 2
    const midY = (srcCoord.y + tgtCoord.y) / 2

    result.push({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      path,
      midX,
      midY,
      isRunning: isRunning.value && srcNode.status === 'completed' && tgtNode.status === 'running',
    })
  }
  return result
})

// 鼠标拖拽移动节点逻辑
const startDragNode = (node: WorkflowNode, e: MouseEvent) => {
  if ((e.target as HTMLElement).closest('.port-handle') || (e.target as HTMLElement).closest('button')) {
    return
  }
  selectedNodeId.value = node.id
  isDraggingNode.value = true
  draggedNodeId.value = node.id

  const rect = canvasRef.value?.getBoundingClientRect()
  if (rect) {
    dragOffset.value = {
      x: e.clientX - rect.left - node.x,
      y: e.clientY - rect.top - node.y,
    }
  }
}

const onCanvasMouseMove = (e: MouseEvent) => {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return

  mousePos.value = {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top,
  }

  // 正在拖拽节点
  if (isDraggingNode.value && draggedNodeId.value) {
    const node = workflow.value.nodes.find(n => n.id === draggedNodeId.value)
    if (node) {
      node.x = Math.max(20, mousePos.value.x - dragOffset.value.x)
      node.y = Math.max(20, mousePos.value.y - dragOffset.value.y)
    }
  }
}

const onCanvasMouseUp = () => {
  isDraggingNode.value = false
  draggedNodeId.value = null
  connectingSourceId.value = null
}

// 端口连线交互：开始从输出端口拉线
const startConnecting = (nodeId: string, e: MouseEvent) => {
  e.stopPropagation()
  connectingSourceId.value = nodeId
}

// 端口连线交互：松开吸附在目标输入端口
const finishConnecting = (targetNodeId: string, e: MouseEvent) => {
  e.stopPropagation()
  if (!connectingSourceId.value || connectingSourceId.value === targetNodeId) {
    connectingSourceId.value = null
    return
  }

  // 避免重复连线
  const exists = workflow.value.edges.some(
    e => e.source === connectingSourceId.value && e.target === targetNodeId
  )
  if (!exists) {
    workflow.value.edges.push({
      id: `edge_${Date.now()}`,
      source: connectingSourceId.value,
      target: targetNodeId,
      source_handle: 'output',
      target_handle: 'input',
    })
    message.success('已建立节点连接！')
  }
  connectingSourceId.value = null
}

// 删除连线
const deleteEdge = (edgeId: string) => {
  workflow.value.edges = workflow.value.edges.filter(e => e.id !== edgeId)
}

// 删除节点及其关联的所有连线
const deleteNode = (nodeId: string) => {
  workflow.value.nodes = workflow.value.nodes.filter(n => n.id !== nodeId)
  workflow.value.edges = workflow.value.edges.filter(e => e.source !== nodeId && e.target !== nodeId)
  if (selectedNodeId.value === nodeId) {
    selectedNodeId.value = null
  }
}

// 向画布添加新节点
const addNodeToCanvas = (type: WorkflowNode['type']) => {
  const meta = NODE_TYPES[type]
  const id = `node_${type}_${Date.now().toString(36)}`
  const newNode: WorkflowNode = {
    id,
    type,
    title: meta.label,
    x: 100 + (workflow.value.nodes.length % 5) * 60,
    y: 120 + (workflow.value.nodes.length % 4) * 50,
    config: {},
  }

  // 赋初始默认配置
  if (type === 'timer') {
    newNode.config = { schedule_type: 'weekly', day_of_week: '5', time: '18:00', cron_expression: '0 18 * * 5' }
  } else if (type === 'crawler') {
    newNode.config = { url: 'https://news.ycombinator.com', timeout: 15 }
  } else if (type === 'rag') {
    newNode.config = { query: '技术前沿与智能体进展', top_k: 3, category: 'default' }
  } else if (type === 'llm') {
    newNode.config = {
      model: 'deepseek-chat',
      temperature: 0.5,
      system_prompt: '你是一个专业周报分析师。',
      prompt_template: '根据以下内容撰写周报：\n{{crawler_data}}\n\n{{rag_data}}',
    }
  } else if (type === 'feishu') {
    newNode.config = { webhook_url: '', title: '📊 NexusDesk AI 行业前沿深度洞察周报' }
  } else if (type === 'email') {
    newNode.config = { recipient: 'team@example.com' }
  }

  workflow.value.nodes.push(newNode)
  selectedNodeId.value = id
  message.success(`已添加「${meta.label}」节点`)
}

// 获取并加载工作流列表
const fetchWorkflows = async () => {
  try {
    const list = await apiClient.getWorkflows()
    if (list && list.length > 0) {
      workflowList.value = list
      workflow.value = list[0]
    }
  } catch (err) {
    console.error('获取工作流列表失败:', err)
  }
}

// 切换选中的工作流
const switchWorkflow = (wf: WorkflowItem) => {
  workflow.value = JSON.parse(JSON.stringify(wf))
  selectedNodeId.value = null
  executionResults.value = null
}

// 保存当前工作流配置
const saveCurrentWorkflow = async () => {
  isSaving.value = true
  try {
    await apiClient.saveWorkflow(workflow.value)
    message.success('工作流配置已持久化保存！')
    await fetchWorkflows()
  } catch (err: any) {
    message.error(err.message || '保存失败')
  } finally {
    isSaving.value = false
  }
}

// 切换周期性自动调度开关
const toggleSchedule = async () => {
  const nextStatus = !workflow.value.is_scheduled
  try {
    await apiClient.toggleWorkflowSchedule(workflow.value.id, nextStatus)
    workflow.value.is_scheduled = nextStatus
    message.success(nextStatus ? '✅ 已激活后台周期性定时自动化调度！' : '已暂停后台定时调度')
  } catch (err: any) {
    message.error(err.message || '切换调度失败')
  }
}

// 触发单次全链路调试运行
const runCurrentWorkflow = async () => {
  if (isRunning.value) return
  isRunning.value = true
  showResultDrawer.value = true
  executionLogs.value = []

  // 重置各节点运行状态
  workflow.value.nodes.forEach(n => {
    n.status = 'idle'
    n.output = null
    n.error = undefined
  })

  try {
    // 视觉反馈：设置首个节点进入 running
    if (workflow.value.nodes.length > 0) {
      workflow.value.nodes[0].status = 'running'
    }

    const res = await apiClient.runWorkflow(workflow.value)
    executionResults.value = res
    executionLogs.value = res.logs || []

    // 同步节点执行结果
    if (res.results) {
      for (const [nid, result] of Object.entries(res.results) as [string, any][]) {
        const node = workflow.value.nodes.find(n => n.id === nid)
        if (node) {
          node.status = result.status
          node.output = result.output
          node.error = result.error
        }
      }
    }

    if (res.success) {
      message.success(`工作流全链路执行成功！总耗时 ${res.total_duration_sec}s`)
    } else {
      message.warning('工作流执行完成，部分节点遇到异常')
    }
  } catch (err: any) {
    message.error(`执行失败: ${err.message || err}`)
  } finally {
    isRunning.value = false
  }
}

// 一键复制代码
const copyText = (txt: string) => {
  navigator.clipboard.writeText(txt)
  message.success('已复制到剪贴板')
}

onMounted(() => {
  fetchWorkflows()
})
</script>

<template>
  <div class="h-full w-full flex flex-col bg-gray-50 dark:bg-zinc-950 overflow-hidden select-none">
    <!-- 顶部工作流控制栏 -->
    <header class="h-14 flex-shrink-0 flex items-center justify-between px-5 border-b border-gray-200 dark:border-zinc-800 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md z-20">
      <!-- 左侧：工作流名称与模版选择 -->
      <div class="flex items-center gap-3 min-w-0">
        <div class="w-8 h-8 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200/80 dark:border-indigo-800/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
          <Layers class="w-4 h-4" />
        </div>
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-xs font-bold text-gray-900 dark:text-white truncate max-w-[280px]">
              {{ workflow.name }}
            </span>
            <span
              class="px-2 py-0.5 rounded-full text-[10px] font-medium border"
              :class="workflow.is_scheduled ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800' : 'bg-gray-100 dark:bg-zinc-800 text-gray-500 border-gray-200 dark:border-zinc-700'"
            >
              {{ workflow.is_scheduled ? '● 定时调度中' : '未开启调度' }}
            </span>
          </div>
          <p class="text-[10px] text-gray-400 dark:text-zinc-500 truncate max-w-[420px]">
            {{ workflow.description }}
          </p>
        </div>
      </div>

      <!-- 右侧：快捷操作 (添加节点、保存、调度、调试运行) -->
      <div class="flex items-center gap-2.5">
        <!-- 节点添加抽屉菜单 -->
        <div class="relative group">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-gray-100 hover:bg-gray-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-gray-800 dark:text-zinc-200 transition-colors cursor-pointer"
          >
            <Plus class="w-3.5 h-3.5" />
            <span>添加节点</span>
          </button>
          <!-- 悬浮下拉菜单 -->
          <div class="hidden group-hover:block absolute right-0 top-full pt-1.5 z-50 w-52">
            <div class="p-1.5 rounded-xl bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 shadow-xl space-y-1">
              <button
                v-for="(meta, type) in NODE_TYPES"
                :key="type"
                @click="addNodeToCanvas(type as any)"
                class="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer text-xs"
              >
                <component :is="meta.icon" class="w-4 h-4 flex-shrink-0" :class="meta.color" />
                <div>
                  <div class="font-medium text-gray-900 dark:text-white">{{ meta.label }}</div>
                  <div class="text-[10px] text-gray-400">{{ meta.desc }}</div>
                </div>
              </button>
            </div>
          </div>
        </div>

        <!-- 周期自动调度切换 -->
        <button
          @click="toggleSchedule"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors cursor-pointer"
          :class="workflow.is_scheduled ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800' : 'bg-white dark:bg-zinc-900 border-gray-300 dark:border-zinc-700 text-gray-700 dark:text-zinc-300'"
          title="将此编排任务交给后台根据配置的 Cron 周期自动执行"
        >
          <Clock class="w-3.5 h-3.5" />
          <span>{{ workflow.is_scheduled ? '暂停调度' : '开启周期调度' }}</span>
        </button>

        <!-- 保存按钮 -->
        <button
          @click="saveCurrentWorkflow"
          :disabled="isSaving"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-800 text-gray-800 dark:text-zinc-200 transition-colors cursor-pointer"
        >
          <Save class="w-3.5 h-3.5" />
          <span>{{ isSaving ? '保存中...' : '保存编排' }}</span>
        </button>

        <!-- 立即运行测试按钮 -->
        <button
          @click="runCurrentWorkflow"
          :disabled="isRunning"
          class="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white shadow-sm transition-all cursor-pointer disabled:opacity-50"
        >
          <Loader2 v-if="isRunning" class="w-3.5 h-3.5 animate-spin" />
          <Play v-else class="w-3.5 h-3.5 fill-current" />
          <span>{{ isRunning ? '正在全链路执行...' : '立即运行测试' }}</span>
        </button>
      </div>
    </header>

    <!-- 中间主体：可视化点阵画布 + 右侧参数配置抽屉 -->
    <div class="flex-1 relative overflow-hidden flex">
      <!-- 1. 无限点阵画布 -->
      <div
        ref="canvasRef"
        @mousemove="onCanvasMouseMove"
        @mouseup="onCanvasMouseUp"
        class="flex-1 h-full relative overflow-hidden bg-[#fafafa] dark:bg-[#0c0c0e] select-none cursor-crosshair"
        style="background-image: radial-gradient(circle, rgba(160, 160, 160, 0.25) 1px, transparent 1px); background-size: 24px 24px;"
      >
        <!-- 连线 SVG 层 -->
        <svg class="absolute inset-0 w-full h-full pointer-events-none z-10">
          <defs>
            <linearGradient id="edge-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stop-color="#818cf8" />
              <stop offset="100%" stop-color="#c084fc" />
            </linearGradient>
            <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#818cf8" />
            </marker>
          </defs>

          <!-- 已确立的连线 -->
          <g v-for="edge in renderedEdges" :key="edge.id">
            <!-- 底层加宽便于点击/悬停删除 -->
            <path
              :d="edge.path"
              stroke="transparent"
              stroke-width="16"
              class="pointer-events-auto cursor-pointer"
              @click="deleteEdge(edge.id)"
            />
            <!-- 视觉可见连线 -->
            <path
              :d="edge.path"
              stroke="url(#edge-gradient)"
              :stroke-width="edge.isRunning ? '3' : '2'"
              fill="none"
              stroke-linecap="round"
              :stroke-dasharray="edge.isRunning ? '6 4' : 'none'"
              :class="edge.isRunning ? 'animate-flow' : ''"
              marker-end="url(#arrow)"
            />
          </g>

          <!-- 正在拖拽拉扯中的临时连线 -->
          <path
            v-if="connectingSourceId"
            :d="calculateBezierPath(
              getNodePortCoords(workflow.nodes.find(n => n.id === connectingSourceId)!).output.x,
              getNodePortCoords(workflow.nodes.find(n => n.id === connectingSourceId)!).output.y,
              mousePos.x,
              mousePos.y
            )"
            stroke="#6366f1"
            stroke-width="2"
            stroke-dasharray="5 5"
            fill="none"
          />
        </svg>

        <!-- 节点卡片层 -->
        <div
          v-for="node in workflow.nodes"
          :key="node.id"
          @mousedown="startDragNode(node, $event)"
          :style="{
            transform: `translate3d(${node.x}px, ${node.y}px, 0)`,
            width: `${NODE_WIDTH}px`,
          }"
          class="absolute z-20 rounded-2xl bg-white dark:bg-zinc-900 border shadow-md transition-shadow cursor-grab active:cursor-grabbing select-none"
          :class="[
            selectedNodeId === node.id ? 'ring-2 ring-indigo-500 shadow-xl border-indigo-500' : 'border-gray-200 dark:border-zinc-800 hover:border-gray-300 dark:hover:border-zinc-700',
            node.status === 'running' ? 'ring-2 ring-indigo-500 animate-pulse' : '',
            node.status === 'completed' ? 'border-emerald-500' : '',
            node.status === 'error' ? 'border-rose-500' : '',
          ]"
        >
          <!-- 节点顶部标头：图标、标题、状态徽章与删除按钮 -->
          <div
            class="px-3.5 py-2.5 rounded-t-2xl border-b flex items-center justify-between"
            :class="[NODE_TYPES[node.type]?.bg || 'bg-gray-50', NODE_TYPES[node.type]?.border || 'border-gray-200']"
          >
            <div class="flex items-center gap-2 min-w-0">
              <component :is="NODE_TYPES[node.type]?.icon || Sparkles" class="w-4 h-4 flex-shrink-0" :class="NODE_TYPES[node.type]?.color || 'text-gray-600'" />
              <span class="text-xs font-bold text-gray-900 dark:text-white truncate">
                {{ node.title }}
              </span>
            </div>
            
            <div class="flex items-center gap-1.5 flex-shrink-0">
              <!-- 运行状态指示器 -->
              <span v-if="node.status === 'running'" class="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
              <CheckCircle2 v-else-if="node.status === 'completed'" class="w-3.5 h-3.5 text-emerald-500" />
              <AlertCircle v-else-if="node.status === 'error'" class="w-3.5 h-3.5 text-rose-500" />

              <button
                @click.stop="deleteNode(node.id)"
                class="p-1 rounded text-gray-400 hover:text-rose-500 transition-colors"
                title="删除节点"
              >
                <Trash2 class="w-3 h-3" />
              </button>
            </div>
          </div>

          <!-- 节点主体简要参数预览 -->
          <div class="p-3 text-[11px] text-gray-500 dark:text-zinc-400 space-y-1">
            <template v-if="node.type === 'timer'">
              <div>周期: <span class="font-mono text-gray-800 dark:text-zinc-200">每周五 18:00 ({{ node.config.cron_expression }})</span></div>
            </template>
            <template v-else-if="node.type === 'crawler'">
              <div class="truncate">URL: <span class="font-mono text-gray-800 dark:text-zinc-200">{{ node.config.url }}</span></div>
            </template>
            <template v-else-if="node.type === 'rag'">
              <div class="truncate">提炼主题: <span class="text-gray-800 dark:text-zinc-200">{{ node.config.query }}</span></div>
              <div>召回数量: <span class="font-mono text-gray-800 dark:text-zinc-200">Top {{ node.config.top_k }} 切片</span></div>
            </template>
            <template v-else-if="node.type === 'llm'">
              <div>模型: <span class="font-mono text-gray-800 dark:text-zinc-200">{{ node.config.model }}</span></div>
              <div class="truncate">提示词: <span class="text-gray-800 dark:text-zinc-200">{{ node.config.prompt_template }}</span></div>
            </template>
            <template v-else-if="node.type === 'feishu'">
              <div class="truncate">飞书群: <span class="text-gray-800 dark:text-zinc-200">{{ node.config.title }}</span></div>
            </template>
          </div>

          <!-- 左侧输入端口 (Input Port) -->
          <div
            v-if="node.type !== 'timer'"
            @mouseup="finishConnecting(node.id, $event)"
            class="port-handle absolute -left-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-white dark:bg-zinc-900 border-2 border-indigo-500 hover:scale-125 transition-transform cursor-pointer flex items-center justify-center shadow-xs"
            title="连接输入"
          >
            <div class="w-1.5 h-1.5 rounded-full bg-indigo-500" />
          </div>

          <!-- 右侧输出端口 (Output Port) -->
          <div
            v-if="node.type !== 'feishu' && node.type !== 'email'"
            @mousedown="startConnecting(node.id, $event)"
            class="port-handle absolute -right-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-white dark:bg-zinc-900 border-2 border-indigo-500 hover:scale-125 transition-transform cursor-pointer flex items-center justify-center shadow-xs"
            title="按住拖拽连线至下级节点"
          >
            <div class="w-1.5 h-1.5 rounded-full bg-indigo-500" />
          </div>
        </div>
      </div>

      <!-- 2. 右侧节点属性配置面板 (Inspector) -->
      <aside
        v-if="selectedNode"
        class="w-80 border-l border-gray-200 dark:border-zinc-800 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-md flex flex-col z-20 shadow-xl"
      >
        <div class="h-12 px-4 border-b border-gray-200 dark:border-zinc-800 flex items-center justify-between">
          <div class="flex items-center gap-2 text-xs font-bold text-gray-900 dark:text-white">
            <Settings2 class="w-4 h-4 text-indigo-500" />
            <span>节点属性配置</span>
          </div>
          <button @click="selectedNodeId = null" class="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-zinc-200">
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
          <!-- 标题设置 -->
          <div>
            <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">节点显示名称</label>
            <input
              v-model="selectedNode.title"
              class="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent text-gray-900 dark:text-zinc-100"
            />
          </div>

          <!-- 各节点专属参数配置 -->
          <template v-if="selectedNode.type === 'timer'">
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">调度频率</label>
              <select
                v-model="selectedNode.config.schedule_type"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent"
              >
                <option value="weekly">每周定时</option>
                <option value="daily">每天定时</option>
                <option value="hourly">每隔N小时</option>
              </select>
            </div>
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">标准 Cron 表达式</label>
              <input
                v-model="selectedNode.config.cron_expression"
                placeholder="0 18 * * 5"
                class="w-full px-3 py-1.5 rounded-lg font-mono border border-gray-300 dark:border-zinc-700 bg-transparent"
              />
              <span class="text-[10px] text-gray-400 mt-1 block">示例：0 18 * * 5 表示每周五下午 18:00 执行</span>
            </div>
          </template>

          <template v-else-if="selectedNode.type === 'crawler'">
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">抓取目标 URL</label>
              <input
                v-model="selectedNode.config.url"
                class="w-full px-3 py-1.5 rounded-lg font-mono border border-gray-300 dark:border-zinc-700 bg-transparent"
              />
            </div>
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">超时时间 (秒)</label>
              <input
                v-model.number="selectedNode.config.timeout"
                type="number"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent"
              />
            </div>
          </template>

          <template v-else-if="selectedNode.type === 'rag'">
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">知识库提炼问题 / 主题</label>
              <textarea
                v-model="selectedNode.config.query"
                rows="2"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent resize-none"
              />
            </div>
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">召回切片数 (Top-K)</label>
              <input
                v-model.number="selectedNode.config.top_k"
                type="number"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent"
              />
            </div>
          </template>

          <template v-else-if="selectedNode.type === 'llm'">
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">大语言模型</label>
              <input
                v-model="selectedNode.config.model"
                class="w-full px-3 py-1.5 rounded-lg font-mono border border-gray-300 dark:border-zinc-700 bg-transparent"
              />
            </div>
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">系统人设 (System Prompt)</label>
              <textarea
                v-model="selectedNode.config.system_prompt"
                rows="2"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent resize-none"
              />
            </div>
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">提示词模版 (支持变量插值)</label>
              <textarea
                v-model="selectedNode.config.prompt_template"
                rows="5"
                class="w-full px-3 py-1.5 rounded-lg font-mono text-[11px] border border-gray-300 dark:border-zinc-700 bg-transparent"
              />
              <div class="flex items-center gap-1.5 mt-1.5">
                <span class="text-[10px] text-gray-400">可用插值标签:</span>
                <code @click="selectedNode.config.prompt_template += ' {{crawler_data}}'" class="px-1 py-0.5 rounded bg-blue-50 dark:bg-blue-950 text-blue-600 text-[10px] cursor-pointer">+ crawler_data</code>
                <code @click="selectedNode.config.prompt_template += ' {{rag_data}}'" class="px-1 py-0.5 rounded bg-purple-50 dark:bg-purple-950 text-purple-600 text-[10px] cursor-pointer">+ rag_data</code>
              </div>
            </div>
          </template>

          <template v-else-if="selectedNode.type === 'feishu'">
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">飞书自定义机器人 Webhook URL</label>
              <input
                v-model="selectedNode.config.webhook_url"
                placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                class="w-full px-3 py-1.5 rounded-lg font-mono text-[11px] border border-gray-300 dark:border-zinc-700 bg-transparent"
              />
              <span class="text-[10px] text-gray-400 mt-1 block">未填写时以模拟演练模式执行，不打扰真实群聊</span>
            </div>
            <div>
              <label class="block font-semibold text-gray-700 dark:text-zinc-300 mb-1">通知卡片大标题</label>
              <input
                v-model="selectedNode.config.title"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-zinc-700 bg-transparent"
              />
            </div>
          </template>
        </div>
      </aside>
    </div>

    <!-- 底部执行结果与产物抽屉面板 (可折叠展示) -->
    <div
      v-if="showResultDrawer"
      class="h-64 flex-shrink-0 border-t border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xl flex flex-col z-30 transition-all"
    >
      <div class="h-10 px-4 border-b border-gray-200 dark:border-zinc-800 flex items-center justify-between text-xs font-semibold bg-gray-50/70 dark:bg-zinc-800/40">
        <div class="flex items-center gap-2 text-gray-800 dark:text-zinc-200">
          <Play class="w-3.5 h-3.5 text-indigo-500 fill-current" />
          <span>工作流全链路执行控制台与阶段产物</span>
          <span v-if="executionResults" class="text-[10px] text-gray-400 font-normal">
            (总耗时: {{ executionResults.total_duration_sec }}s)
          </span>
        </div>
        <button @click="showResultDrawer = false" class="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-zinc-200">
          <X class="w-4 h-4" />
        </button>
      </div>

      <div class="flex-1 flex overflow-hidden">
        <!-- 左侧：执行步骤日志流 -->
        <div class="w-1/3 border-r border-gray-200 dark:border-zinc-800 p-3 overflow-y-auto space-y-1.5 font-mono text-[11px]">
          <div
            v-for="(log, idx) in executionLogs"
            :key="idx"
            class="flex items-start gap-2 py-1 px-2 rounded"
            :class="log.status === 'completed' ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-50/50 dark:bg-emerald-950/20' : (log.status === 'error' ? 'text-rose-600 bg-rose-50/50' : 'text-gray-600 dark:text-zinc-400')"
          >
            <span class="text-gray-400 flex-shrink-0">{{ log.time }}</span>
            <span class="font-bold flex-shrink-0">[{{ log.node_title }}]</span>
            <span class="truncate flex-1">{{ log.message }}</span>
          </div>
          <div v-if="executionLogs.length === 0" class="text-gray-400 text-center py-8">
            点击上方「立即运行测试」开始追踪执行
          </div>
        </div>

        <!-- 右侧：最终产物预览 (周报结果或飞书响应) -->
        <div class="flex-1 p-4 overflow-y-auto text-xs space-y-3">
          <div v-if="executionResults?.results?.node_llm?.output" class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="font-bold text-gray-900 dark:text-white flex items-center gap-1.5">
                <Sparkles class="w-4 h-4 text-emerald-500" />
                <span>AI 深度合成周报交付预览</span>
              </span>
              <button
                @click="copyText(executionResults.results.node_llm.output)"
                class="flex items-center gap-1 px-2 py-1 rounded border border-gray-200 dark:border-zinc-700 hover:bg-gray-100 text-[11px] cursor-pointer"
              >
                <Copy class="w-3 h-3" />
                <span>复制周报内容</span>
              </button>
            </div>
            <pre class="p-3 rounded-xl bg-gray-50 dark:bg-zinc-950 border border-gray-200 dark:border-zinc-800 font-sans whitespace-pre-wrap leading-relaxed text-gray-800 dark:text-zinc-200">{{ executionResults.results.node_llm.output }}</pre>
          </div>
          <div v-else class="text-center text-gray-400 py-12 text-xs">
            等待全链路执行完成生成报告...
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes flow {
  from {
    stroke-dashoffset: 20;
  }
  to {
    stroke-dashoffset: 0;
  }
}

.animate-flow {
  animation: flow 1s linear infinite;
}
</style>
