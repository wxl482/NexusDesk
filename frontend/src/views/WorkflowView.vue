<script setup lang="ts">
/**
 * NexusDesk 可视化节点编排工作流画布 (Workflow Canvas)
 * 对标 Dify / ComfyUI 风格：
 * 1. 无限点阵网格画布，支持按住空格/中键/背景平移 (Pan) 与鼠标滚轮平滑缩放 (Zoom)；
 * 2. 窗口级高帧率平滑拖拽手感 (零掉帧、零失焦、自动吸附)；
 * 3. 完美修复 SVG 贝塞尔连线 (杜绝黑色色块填充，支持渐变流光、状态流转与中点悬浮删除)；
 * 4. 涵盖定时器、网页爬虫、知识库语义提炼、大模型周报撰写、飞书通知全流程闭环。
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
  Maximize2,
  ZoomIn,
  ZoomOut,
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
const hoveredEdgeId = ref<string | null>(null)

// 画布视图状态（无限画布平移与缩放）
const canvasRef = ref<HTMLDivElement | null>(null)
const panX = ref(40)
const panY = ref(40)
const zoom = ref(1.0)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, initialPanX: 0, initialPanY: 0 })
const isSpacePressed = ref(false)

// 节点拖拽状态
const isDraggingNode = ref(false)
const draggedNodeId = ref<string | null>(null)
const dragOffset = ref({ x: 0, y: 0 })

// 连线创建状态
const connectingSourceId = ref<string | null>(null)
const hoveredTargetPortNodeId = ref<string | null>(null)
const mouseWorldPos = ref({ x: 0, y: 0 })

// 执行状态与日志抽屉
const isRunning = ref(false)
const isSaving = ref(false)
const showResultDrawer = ref(false)
const executionResults = ref<any>(null)
const executionLogs = ref<any[]>([])

// 节点卡片尺寸常量 (用于计算端口世界坐标)
const NODE_WIDTH = 260
const NODE_HEIGHT = 120

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

// 获取节点的输入与输出端口世界坐标
const getNodePortCoords = (node: WorkflowNode) => {
  return {
    input: { x: node.x, y: node.y + NODE_HEIGHT / 2 },
    output: { x: node.x + NODE_WIDTH, y: node.y + NODE_HEIGHT / 2 },
  }
}

// 计算贝塞尔连线路径 (水平 S 型控制曲线)
const calculateBezierPath = (x1: number, y1: number, x2: number, y2: number) => {
  const dx = Math.max(Math.abs(x2 - x1) * 0.5, 45)
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

// 无限网格点阵背景动态样式
const canvasGridStyle = computed(() => {
  const size = 24 * zoom.value
  return {
    backgroundPosition: `${panX.value}px ${panY.value}px`,
    backgroundSize: `${size}px ${size}px`,
  }
})

// 视口内容变换样式
const worldTransformStyle = computed(() => ({
  transform: `translate3d(${panX.value}px, ${panY.value}px, 0) scale(${zoom.value})`,
  transformOrigin: '0 0',
}))

// 快捷操作：缩放与视图复位
const zoomIn = () => {
  zoom.value = Math.min(zoom.value * 1.15, 2.2)
}
const zoomOut = () => {
  zoom.value = Math.max(zoom.value * 0.85, 0.35)
}
const resetZoom = () => {
  zoom.value = 1.0
}

// 视图自适应居中全部节点
const fitView = () => {
  if (workflow.value.nodes.length === 0) {
    panX.value = 60
    panY.value = 60
    zoom.value = 1.0
    return
  }

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const n of workflow.value.nodes) {
    minX = Math.min(minX, n.x)
    minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x + NODE_WIDTH)
    maxY = Math.max(maxY, n.y + NODE_HEIGHT)
  }

  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return

  const padding = 100
  const graphWidth = maxX - minX + padding * 2
  const graphHeight = maxY - minY + padding * 2

  const scaleX = rect.width / graphWidth
  const scaleY = rect.height / graphHeight
  const newZoom = Math.min(Math.max(Math.min(scaleX, scaleY), 0.5), 1.2)

  zoom.value = newZoom
  panX.value = (rect.width - (maxX - minX) * newZoom) / 2 - minX * newZoom
  panY.value = (rect.height - (maxY - minY) * newZoom) / 2 - minY * newZoom
}

// 鼠标滚轮缩放画布 (聚焦于鼠标指针位置)
const onCanvasWheel = (e: WheelEvent) => {
  e.preventDefault()
  const factor = e.deltaY < 0 ? 1.08 : 0.92
  const newZoom = Math.min(Math.max(zoom.value * factor, 0.35), 2.2)
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return

  const mouseCanvasX = e.clientX - rect.left
  const mouseCanvasY = e.clientY - rect.top

  // 保持鼠标指向的世界坐标不动进行缩放
  panX.value = mouseCanvasX - (mouseCanvasX - panX.value) * (newZoom / zoom.value)
  panY.value = mouseCanvasY - (mouseCanvasY - panY.value) * (newZoom / zoom.value)
  zoom.value = newZoom
}

// 画布背景按下：触发画布平移
const onCanvasMouseDown = (e: MouseEvent) => {
  // 如果点击的是节点、按钮或端口，不触发画布平移
  if ((e.target as HTMLElement).closest('.workflow-node') ||
      (e.target as HTMLElement).closest('.port-handle') ||
      (e.target as HTMLElement).closest('button') ||
      (e.target as HTMLElement).closest('input')) {
    return
  }

  // 左键点击背景或中键拖动画布
  if (e.button === 0 || e.button === 1 || isSpacePressed.value) {
    selectedNodeId.value = null
    connectingSourceId.value = null
    isPanning.value = true
    panStart.value = {
      x: e.clientX,
      y: e.clientY,
      initialPanX: panX.value,
      initialPanY: panY.value,
    }
    window.addEventListener('mousemove', onWindowMouseMove)
    window.addEventListener('mouseup', onWindowMouseUp)
  }
}

// 启动节点拖拽 (加入全局 window 监听，彻底杜绝掉帧与脱手)
const startDragNode = (node: WorkflowNode, e: MouseEvent) => {
  if ((e.target as HTMLElement).closest('.port-handle') ||
      (e.target as HTMLElement).closest('button')) {
    return
  }
  e.stopPropagation()

  selectedNodeId.value = node.id
  draggedNodeId.value = node.id
  isDraggingNode.value = true

  const rect = canvasRef.value?.getBoundingClientRect()
  if (rect) {
    const worldMouseX = (e.clientX - rect.left - panX.value) / zoom.value
    const worldMouseY = (e.clientY - rect.top - panY.value) / zoom.value
    dragOffset.value = {
      x: worldMouseX - node.x,
      y: worldMouseY - node.y,
    }
  }

  window.addEventListener('mousemove', onWindowMouseMove)
  window.addEventListener('mouseup', onWindowMouseUp)
}

// 全局鼠标移动处理
const onWindowMouseMove = (e: MouseEvent) => {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return

  // 更新当前世界坐标
  const worldMouseX = (e.clientX - rect.left - panX.value) / zoom.value
  const worldMouseY = (e.clientY - rect.top - panY.value) / zoom.value
  mouseWorldPos.value = { x: worldMouseX, y: worldMouseY }

  // 1. 处理节点拖动
  if (isDraggingNode.value && draggedNodeId.value) {
    const node = workflow.value.nodes.find(n => n.id === draggedNodeId.value)
    if (node) {
      node.x = Math.round(worldMouseX - dragOffset.value.x)
      node.y = Math.round(worldMouseY - dragOffset.value.y)
    }
    return
  }

  // 2. 处理画布平移
  if (isPanning.value) {
    panX.value = panStart.value.initialPanX + (e.clientX - panStart.value.x)
    panY.value = panStart.value.initialPanY + (e.clientY - panStart.value.y)
    return
  }
}

// 全局鼠标松开处理
const onWindowMouseUp = () => {
  isDraggingNode.value = false
  draggedNodeId.value = null
  isPanning.value = false

  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
}

// 端口连线交互：开始从输出端口拉线
const startConnecting = (nodeId: string, e: MouseEvent) => {
  e.stopPropagation()
  connectingSourceId.value = nodeId
  const rect = canvasRef.value?.getBoundingClientRect()
  if (rect) {
    mouseWorldPos.value = {
      x: (e.clientX - rect.left - panX.value) / zoom.value,
      y: (e.clientY - rect.top - panY.value) / zoom.value,
    }
  }
  window.addEventListener('mousemove', onWindowMouseMove)
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
    edge => edge.source === connectingSourceId.value && edge.target === targetNodeId
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
  window.removeEventListener('mousemove', onWindowMouseMove)
}

// 取消连线拉取
const cancelConnecting = () => {
  connectingSourceId.value = null
  window.removeEventListener('mousemove', onWindowMouseMove)
}

// 删除连线
const deleteEdge = (edgeId: string) => {
  workflow.value.edges = workflow.value.edges.filter(e => e.id !== edgeId)
  message.info('已移除连线')
}

// 删除节点及其关联的所有连线
const deleteNode = (nodeId: string) => {
  workflow.value.nodes = workflow.value.nodes.filter(n => n.id !== nodeId)
  workflow.value.edges = workflow.value.edges.filter(e => e.source !== nodeId && e.target !== nodeId)
  if (selectedNodeId.value === nodeId) {
    selectedNodeId.value = null
  }
  message.info('已删除节点')
}

// 向画布添加新节点
const addNodeToCanvas = (type: WorkflowNode['type']) => {
  const meta = NODE_TYPES[type]
  const id = `node_${type}_${Date.now().toString(36)}`
  
  // 在当前视野中央偏右处生成节点
  const rect = canvasRef.value?.getBoundingClientRect()
  const centerX = rect ? (rect.width / 2 - panX.value) / zoom.value : 300
  const centerY = rect ? (rect.height / 2 - panY.value) / zoom.value : 200

  const newNode: WorkflowNode = {
    id,
    type,
    title: meta.label,
    x: Math.round(centerX - NODE_WIDTH / 2 + (workflow.value.nodes.length % 4) * 20),
    y: Math.round(centerY - NODE_HEIGHT / 2 + (workflow.value.nodes.length % 4) * 20),
    config: {},
  }

  if (type === 'timer') {
    newNode.config = { schedule_type: 'weekly', day_of_week: '5', time: '18:00', cron_expression: '0 18 * * 5' }
  } else if (type === 'crawler') {
    newNode.config = { url: 'https://news.ycombinator.com', timeout: 15 }
  } else if (type === 'rag') {
    newNode.config = { query: '技术前沿架构与大模型智能体演进', top_k: 3, category: 'default' }
  } else if (type === 'llm') {
    newNode.config = {
      model: 'deepseek-chat',
      temperature: 0.5,
      system_prompt: '你是一个专业周报分析师。',
      prompt_template: '根据以下最新资料撰写周报：\n{{crawler_data}}\n\n{{rag_data}}',
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
      setTimeout(() => fitView(), 100)
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
  setTimeout(() => fitView(), 80)
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

  // 重置各节点运行状态为待命
  workflow.value.nodes.forEach(n => {
    n.status = 'idle'
    n.output = null
    n.error = undefined
  })

  try {
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
      message.success(`🎉 工作流全链路执行成功！总耗时 ${res.total_duration_sec}s`)
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

// 快捷键监听 (空格平移画布)
const onKeyDown = (e: KeyboardEvent) => {
  if (e.code === 'Space' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
    isSpacePressed.value = true
  }
}
const onKeyUp = (e: KeyboardEvent) => {
  if (e.code === 'Space') {
    isSpacePressed.value = false
  }
}

onMounted(() => {
  fetchWorkflows()
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
})
</script>

<template>
  <div class="h-full w-full flex flex-col bg-gray-50 dark:bg-zinc-950 overflow-hidden select-none">
    <!-- 顶部工作流控制栏 -->
    <header class="h-14 flex-shrink-0 flex items-center justify-between px-5 border-b border-gray-200 dark:border-zinc-800 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-md z-20">
      <!-- 左侧：工作流名称与模版选择 -->
      <div class="flex items-center gap-3 min-w-0">
        <div class="w-8 h-8 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200/80 dark:border-indigo-800/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400 flex-shrink-0">
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
        <!-- 节点添加菜单 -->
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

        <!-- 开启/关闭周期定时调度 -->
        <button
          @click="toggleSchedule"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer"
          :class="workflow.is_scheduled
            ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400 border-amber-300 dark:border-amber-800 hover:bg-amber-100'
            : 'bg-white dark:bg-zinc-800 text-gray-700 dark:text-zinc-300 border-gray-200 dark:border-zinc-700 hover:bg-gray-50 dark:hover:bg-zinc-700'"
        >
          <Clock class="w-3.5 h-3.5" />
          <span>{{ workflow.is_scheduled ? '暂停调度' : '开启周期调度' }}</span>
        </button>

        <!-- 保存当前工作流 -->
        <button
          @click="saveCurrentWorkflow"
          :disabled="isSaving"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 text-gray-700 dark:text-zinc-300 hover:bg-gray-50 dark:hover:bg-zinc-700 transition-colors cursor-pointer disabled:opacity-50"
        >
          <Loader2 v-if="isSaving" class="w-3.5 h-3.5 animate-spin" />
          <Save v-else class="w-3.5 h-3.5" />
          <span>保存编排</span>
        </button>

        <!-- 立即运行测试 -->
        <button
          @click="runCurrentWorkflow"
          :disabled="isRunning"
          class="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 active:scale-95 shadow-sm transition-all cursor-pointer disabled:opacity-50"
        >
          <Loader2 v-if="isRunning" class="w-3.5 h-3.5 animate-spin" />
          <Play v-else class="w-3.5 h-3.5 fill-current" />
          <span>{{ isRunning ? '全链路运行中...' : '立即运行测试' }}</span>
        </button>
      </div>
    </header>

    <!-- 中间主体：可视化无限点阵画布 + 右侧参数配置抽屉 -->
    <div class="flex-1 relative overflow-hidden flex">
      <!-- 1. 无限点阵画布 -->
      <div
        ref="canvasRef"
        @mousedown="onCanvasMouseDown"
        @wheel="onCanvasWheel"
        class="flex-1 h-full relative overflow-hidden bg-[#f8f9fa] dark:bg-[#09090b] select-none"
        :class="[
          isSpacePressed || isPanning ? 'cursor-grab active:cursor-grabbing' : 'cursor-default',
          connectingSourceId ? 'cursor-crosshair' : ''
        ]"
        :style="{
          backgroundImage: 'radial-gradient(circle, rgba(140, 140, 160, 0.28) 1.2px, transparent 1.2px)',
          ...canvasGridStyle
        }"
      >
        <!-- 视口缩放平移内容容器 (SVG 连线 + 节点卡片) -->
        <div
          class="absolute inset-0 w-full h-full pointer-events-none"
          :style="worldTransformStyle"
        >
          <!-- 连线 SVG 层 -->
          <svg class="absolute inset-0 w-[5000px] h-[5000px] pointer-events-none z-0 overflow-visible">
            <defs>
              <linearGradient id="edge-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#6366f1" />
                <stop offset="100%" stop-color="#a855f7" />
              </linearGradient>
              <marker id="arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#a855f7" />
              </marker>
            </defs>

            <!-- 已确立的连线 -->
            <g
              v-for="edge in renderedEdges"
              :key="edge.id"
              class="pointer-events-auto"
              @mouseenter="hoveredEdgeId = edge.id"
              @mouseleave="hoveredEdgeId = null"
            >
              <!-- 底层加宽透明探测区域 (绝对保证 fill="none"，防止黑色大块产生) -->
              <path
                :d="edge.path"
                stroke="transparent"
                stroke-width="22"
                fill="none"
                class="cursor-pointer"
                @click="deleteEdge(edge.id)"
              />
              <!-- 视觉可见连线 -->
              <path
                :d="edge.path"
                :stroke="hoveredEdgeId === edge.id ? '#ef4444' : 'url(#edge-gradient)'"
                :stroke-width="edge.isRunning ? '3' : (hoveredEdgeId === edge.id ? '2.5' : '2')"
                fill="none"
                stroke-linecap="round"
                :stroke-dasharray="edge.isRunning ? '8 6' : 'none'"
                :class="edge.isRunning ? 'animate-flow' : ''"
                marker-end="url(#arrow)"
                class="transition-colors duration-200"
              />
            </g>

            <!-- 正在拖拽拉扯中的临时连线 (绝对保证 fill="none") -->
            <path
              v-if="connectingSourceId"
              :d="calculateBezierPath(
                getNodePortCoords(workflow.nodes.find(n => n.id === connectingSourceId)!).output.x,
                getNodePortCoords(workflow.nodes.find(n => n.id === connectingSourceId)!).output.y,
                mouseWorldPos.x,
                mouseWorldPos.y
              )"
              stroke="#6366f1"
              stroke-width="2.5"
              stroke-dasharray="6 4"
              fill="none"
              stroke-linecap="round"
              class="animate-pulse"
            />
          </svg>

          <!-- 节点卡片层 -->
          <div
            v-for="node in workflow.nodes"
            :key="node.id"
            class="workflow-node absolute pointer-events-auto transition-shadow"
            :style="{
              left: `${node.x}px`,
              top: `${node.y}px`,
              width: `${NODE_WIDTH}px`,
              zIndex: draggedNodeId === node.id ? 40 : (selectedNodeId === node.id ? 30 : 10),
            }"
            @mousedown="startDragNode(node, $event)"
          >
            <!-- 节点主体卡片 -->
            <div
              class="relative rounded-2xl border bg-white/95 dark:bg-zinc-900/95 backdrop-blur-md transition-all duration-150 cursor-grab active:cursor-grabbing group select-none"
              :class="[
                selectedNodeId === node.id
                  ? 'border-indigo-500 shadow-xl ring-2 ring-indigo-500/20'
                  : 'border-gray-200/90 dark:border-zinc-800 shadow-sm hover:shadow-md hover:border-gray-300 dark:hover:border-zinc-700',
                node.status === 'running' ? 'border-amber-400 ring-2 ring-amber-400/40 shadow-amber-500/10' : '',
                node.status === 'completed' ? 'border-emerald-500 ring-1 ring-emerald-500/30' : '',
                node.status === 'error' ? 'border-rose-500 ring-2 ring-rose-500/30' : ''
              ]"
            >
              <!-- 卡片头部 -->
              <div class="px-3.5 py-2.5 border-b border-gray-100 dark:border-zinc-800/80 flex items-center justify-between">
                <div class="flex items-center gap-2 min-w-0">
                  <div
                    class="w-6 h-6 rounded-md flex items-center justify-center border flex-shrink-0"
                    :class="[NODE_TYPES[node.type]?.bg, NODE_TYPES[node.type]?.border]"
                  >
                    <component :is="NODE_TYPES[node.type]?.icon" class="w-3.5 h-3.5" :class="NODE_TYPES[node.type]?.color" />
                  </div>
                  <span class="text-xs font-bold text-gray-800 dark:text-zinc-200 truncate">
                    {{ node.title }}
                  </span>
                </div>

                <!-- 状态与快捷删除 -->
                <div class="flex items-center gap-1.5 flex-shrink-0">
                  <span v-if="node.status === 'running'" class="flex items-center text-amber-500 text-[10px]">
                    <Loader2 class="w-3 h-3 animate-spin" />
                  </span>
                  <span v-else-if="node.status === 'completed'" class="flex items-center text-emerald-500 text-[10px]">
                    <CheckCircle2 class="w-3.5 h-3.5" />
                  </span>
                  <span v-else-if="node.status === 'error'" class="flex items-center text-rose-500 text-[10px]">
                    <AlertCircle class="w-3.5 h-3.5" />
                  </span>

                  <button
                    @click.stop="deleteNode(node.id)"
                    class="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-rose-500 p-0.5 rounded transition-all cursor-pointer"
                    title="删除节点"
                  >
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              <!-- 卡片核心参数简报 -->
              <div class="px-3.5 py-2 text-[11px] text-gray-600 dark:text-zinc-400 space-y-1">
                <template v-if="node.type === 'timer'">
                  <div class="truncate">周期: {{ node.config.cron_expression || '每周五 18:00 (0 18 * * 5)' }}</div>
                </template>
                <template v-else-if="node.type === 'crawler'">
                  <div class="truncate text-gray-500 font-mono text-[10px]">URL: {{ node.config.url || 'https://news.ycombinator.com' }}</div>
                </template>
                <template v-else-if="node.type === 'rag'">
                  <div class="truncate">提炼主题: {{ node.config.query || '技术前沿架构与大模型演进' }}</div>
                  <div class="text-[10px] text-gray-400">召回数量: Top {{ node.config.top_k || 3 }} 切片</div>
                </template>
                <template v-else-if="node.type === 'llm'">
                  <div class="truncate font-mono text-[10px]">模型: {{ node.config.model || 'deepseek-chat' }}</div>
                  <div class="truncate text-gray-400 text-[10px]">提示词: {{ node.config.prompt_template?.slice(0, 22) }}...</div>
                </template>
                <template v-else-if="node.type === 'feishu'">
                  <div class="truncate">通道: {{ node.config.webhook_url ? '已配置 Webhook' : '模拟推送/待填 Webhook' }}</div>
                </template>
                <template v-else-if="node.type === 'email'">
                  <div class="truncate">收件: {{ node.config.recipient || 'team@example.com' }}</div>
                </template>
              </div>

              <!-- 输入端口 (左侧吸附点) -->
              <div
                v-if="node.type !== 'timer'"
                class="port-handle absolute -left-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-white dark:bg-zinc-800 border-2 border-indigo-500 cursor-crosshair hover:scale-125 transition-transform flex items-center justify-center shadow-md z-30"
                :class="connectingSourceId && connectingSourceId !== node.id ? 'ring-4 ring-emerald-400 animate-pulse' : ''"
                @mouseenter="hoveredTargetPortNodeId = node.id"
                @mouseleave="hoveredTargetPortNodeId = null"
                @mouseup="finishConnecting(node.id, $event)"
                title="输入端口：将前置节点输出连线至此"
              >
                <div class="w-1.5 h-1.5 rounded-full bg-indigo-500 pointer-events-none" />
              </div>

              <!-- 输出端口 (右侧发射点) -->
              <div
                v-if="node.type !== 'feishu' && node.type !== 'email'"
                class="port-handle absolute -right-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-white dark:bg-zinc-800 border-2 border-indigo-500 cursor-crosshair hover:scale-125 transition-transform flex items-center justify-center shadow-md z-30"
                @mousedown="startConnecting(node.id, $event)"
                title="输出端口：按住或点击拉线连接后续节点"
              >
                <div class="w-1.5 h-1.5 rounded-full bg-indigo-500 pointer-events-none" />
              </div>
            </div>
          </div>
        </div>

        <!-- 画布左下角浮动控制条 (缩放/复位/居中自适应) -->
        <div class="absolute bottom-5 left-5 z-20 flex items-center gap-1 p-1 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-md rounded-xl border border-gray-200 dark:border-zinc-800 shadow-lg text-gray-700 dark:text-zinc-300">
          <button
            @click="zoomIn"
            class="p-1.5 hover:bg-gray-100 dark:hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
            title="放大画布"
          >
            <ZoomIn class="w-4 h-4" />
          </button>
          <button
            @click="zoomOut"
            class="p-1.5 hover:bg-gray-100 dark:hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
            title="缩小画布"
          >
            <ZoomOut class="w-4 h-4" />
          </button>
          <button
            @click="resetZoom"
            class="px-2 py-1 text-[11px] font-mono hover:bg-gray-100 dark:hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
            title="重置缩放 100%"
          >
            {{ Math.round(zoom * 100) }}%
          </button>
          <div class="w-px h-3.5 bg-gray-200 dark:bg-zinc-700 mx-0.5" />
          <button
            @click="fitView"
            class="flex items-center gap-1 px-2 py-1 text-[11px] font-medium hover:bg-gray-100 dark:hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
            title="居中自适应全部节点"
          >
            <Maximize2 class="w-3.5 h-3.5" />
            <span>自适应居中</span>
          </button>
        </div>

        <!-- 画布空白处操作小贴士 -->
        <div class="absolute top-4 left-5 z-10 pointer-events-none text-[11px] text-gray-400 dark:text-zinc-500 flex items-center gap-2">
          <span class="px-1.5 py-0.5 rounded bg-gray-200/70 dark:bg-zinc-800 font-mono text-[10px]">空格 + 拖动</span> 或 <span class="px-1.5 py-0.5 rounded bg-gray-200/70 dark:bg-zinc-800 font-mono text-[10px]">滚轮</span> 可无限平移与缩放画布
        </div>
      </div>

      <!-- 2. 右侧参数配置抽屉 (Inspector Panel) -->
      <aside
        v-if="selectedNode"
        class="w-80 flex-shrink-0 border-l border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 flex flex-col z-20 shadow-xl"
      >
        <div class="h-14 px-4 border-b border-gray-200 dark:border-zinc-800 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <component :is="NODE_TYPES[selectedNode.type]?.icon" class="w-4 h-4" :class="NODE_TYPES[selectedNode.type]?.color" />
            <span class="text-xs font-bold text-gray-900 dark:text-white">配置节点：{{ selectedNode.title }}</span>
          </div>
          <button
            @click="selectedNodeId = null"
            class="p-1 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 cursor-pointer"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
          <!-- 节点通用标题 -->
          <div>
            <label class="block text-[11px] font-semibold text-gray-500 mb-1">节点名称</label>
            <input
              v-model="selectedNode.title"
              type="text"
              class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
            />
          </div>

          <!-- 分类型详细参数配置 -->
          <!-- 1. 定时器 -->
          <template v-if="selectedNode.type === 'timer'">
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">Cron 表达式</label>
              <input
                v-model="selectedNode.config.cron_expression"
                type="text"
                placeholder="0 18 * * 5"
                class="w-full font-mono px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
              <p class="text-[10px] text-gray-400 mt-1">例如: 0 18 * * 5 表示每周五下午 18:00 自动触发</p>
            </div>
          </template>

          <!-- 2. 爬虫 -->
          <template v-if="selectedNode.type === 'crawler'">
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">目标抓取 URL</label>
              <input
                v-model="selectedNode.config.url"
                type="text"
                placeholder="https://news.ycombinator.com"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">抓取超时时长 (秒)</label>
              <input
                v-model.number="selectedNode.config.timeout"
                type="number"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
          </template>

          <!-- 3. RAG 知识库检索 -->
          <template v-if="selectedNode.type === 'rag'">
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">检索提炼主题 (Query)</label>
              <input
                v-model="selectedNode.config.query"
                type="text"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">知识召回篇数 (Top-K)</label>
              <input
                v-model.number="selectedNode.config.top_k"
                type="number"
                min="1"
                max="10"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
          </template>

          <!-- 4. LLM 深度合成 -->
          <template v-if="selectedNode.type === 'llm'">
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">调用模型</label>
              <input
                v-model="selectedNode.config.model"
                type="text"
                placeholder="deepseek-chat"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">系统提示词 (System Prompt)</label>
              <textarea
                v-model="selectedNode.config.system_prompt"
                rows="2"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">聚合模版 (支持变量插值)</label>
              <textarea
                v-model="selectedNode.config.prompt_template"
                rows="4"
                class="w-full font-mono text-[11px] px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
              <p class="text-[10px] text-gray-400 mt-1">支持插值: <code class="text-indigo-500">\{\{crawler_data\}\}</code>, <code class="text-indigo-500">\{\{rag_data\}\}</code></p>
            </div>
          </template>

          <!-- 5. 飞书 Webhook -->
          <template v-if="selectedNode.type === 'feishu'">
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">飞书机器人 Webhook URL</label>
              <input
                v-model="selectedNode.config.webhook_url"
                type="text"
                placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
              <p class="text-[10px] text-gray-400 mt-1">留空时将自动启用模拟发信预览</p>
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">通知卡片标题</label>
              <input
                v-model="selectedNode.config.title"
                type="text"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
          </template>

          <!-- 6. 邮件通知 -->
          <template v-if="selectedNode.type === 'email'">
            <div>
              <label class="block text-[11px] font-semibold text-gray-500 mb-1">接收人邮箱地址</label>
              <input
                v-model="selectedNode.config.recipient"
                type="email"
                class="w-full px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
          </template>

          <!-- 节点执行输出明细 -->
          <div v-if="selectedNode.output" class="pt-3 border-t border-gray-200 dark:border-zinc-800">
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-[11px] font-bold text-gray-700 dark:text-zinc-300">上一次运行产物</span>
              <button
                @click="copyText(typeof selectedNode.output === 'object' ? JSON.stringify(selectedNode.output, null, 2) : String(selectedNode.output))"
                class="text-indigo-500 hover:text-indigo-600 flex items-center gap-1 cursor-pointer"
              >
                <Copy class="w-3 h-3" />
                <span>复制</span>
              </button>
            </div>
            <pre class="p-2.5 rounded-lg bg-gray-100 dark:bg-zinc-950 font-mono text-[10px] text-gray-800 dark:text-zinc-200 max-h-48 overflow-y-auto whitespace-pre-wrap break-all">{{ typeof selectedNode.output === 'object' ? JSON.stringify(selectedNode.output, null, 2) : selectedNode.output }}</pre>
          </div>
        </div>
      </aside>
    </div>

    <!-- 底部执行结果与周报预览抽屉 -->
    <div
      v-if="showResultDrawer"
      class="h-64 flex-shrink-0 border-t border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 flex flex-col z-30 shadow-2xl"
    >
      <div class="h-10 px-4 border-b border-gray-200 dark:border-zinc-800 flex items-center justify-between bg-gray-50/50 dark:bg-zinc-900">
        <div class="flex items-center gap-2">
          <Play class="w-3.5 h-3.5 text-indigo-500 fill-current" />
          <span class="text-xs font-bold text-gray-800 dark:text-white">工作流全链路执行控制台与阶段产物</span>
          <span v-if="executionResults" class="text-[10px] text-gray-400">
            (总耗时: {{ executionResults.total_duration_sec }}s)
          </span>
        </div>
        <button
          @click="showResultDrawer = false"
          class="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-zinc-200 rounded cursor-pointer"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <div class="flex-1 flex overflow-hidden">
        <!-- 左半部分：运行流水日志 -->
        <div class="w-1/3 border-r border-gray-200 dark:border-zinc-800 p-3 overflow-y-auto space-y-2 font-mono text-[11px]">
          <div v-if="executionLogs.length === 0" class="text-gray-400 text-center py-8">
            准备执行全链路 DAG 管道...
          </div>
          <div
            v-for="(log, idx) in executionLogs"
            :key="idx"
            class="flex items-start gap-2"
          >
            <span class="text-gray-400 text-[10px]">{{ log.time }}</span>
            <span
              class="font-semibold px-1 rounded text-[10px]"
              :class="log.status === 'completed' ? 'text-emerald-500 bg-emerald-50 dark:bg-emerald-950/40' : (log.status === 'error' ? 'text-rose-500 bg-rose-50 dark:bg-rose-950/40' : 'text-amber-500 bg-amber-50 dark:bg-amber-950/40')"
            >
              [{{ log.node_title }}]
            </span>
            <span class="text-gray-700 dark:text-zinc-300 flex-1 truncate">{{ log.message }}</span>
          </div>
        </div>

        <!-- 右半部分：最终 AI 周报或交付成果呈现 -->
        <div class="flex-1 p-4 overflow-y-auto">
          <div v-if="executionResults?.results?.node_llm?.output" class="space-y-3">
            <div class="flex items-center justify-between pb-2 border-b border-gray-100 dark:border-zinc-800">
              <span class="text-xs font-bold text-gray-900 dark:text-white flex items-center gap-1.5">
                <Sparkles class="w-4 h-4 text-emerald-500" />
                <span>生成结构化周报产物</span>
              </span>
              <button
                @click="copyText(executionResults.results.node_llm.output)"
                class="px-2 py-1 rounded bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 text-[10px] font-semibold flex items-center gap-1 hover:bg-indigo-100 transition-colors cursor-pointer"
              >
                <Copy class="w-3 h-3" />
                <span>复制周报正文</span>
              </button>
            </div>
            <div class="prose prose-xs dark:prose-invert max-w-none text-gray-800 dark:text-zinc-200 whitespace-pre-wrap leading-relaxed font-sans text-xs">
              {{ executionResults.results.node_llm.output }}
            </div>
          </div>
          <div v-else class="h-full flex items-center justify-center text-gray-400 text-xs">
            等待全链路执行完成生成报告...
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes workflow-flow {
  from {
    stroke-dashoffset: 28;
  }
  to {
    stroke-dashoffset: 0;
  }
}

.animate-flow {
  animation: workflow-flow 1.2s linear infinite;
}
</style>
