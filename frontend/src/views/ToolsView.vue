<script setup lang="ts">
/**
 * 智能体技能与扩展能力中心 (ToolsView)
 * 分类清晰、紧凑精致地展示智能助手内置的超能力。
 */
import { ref, onMounted } from 'vue'
import {
  Terminal,
  FolderSync,
  Globe,
  BookOpen,
  Calculator,
  RefreshCw,
  Cpu,
} from 'lucide-vue-next'
import { apiClient } from '../api/client'

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
        description: '以本地向量库中已存的私有文档为事实基准，提供精准严谨的溯源问答。',
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

const isLoading = ref(false)

const handleRefresh = async () => {
  isLoading.value = true
  try {
    await apiClient.getTools()
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  handleRefresh()
})
</script>

<template>
  <div class="flex-1 flex flex-col h-full bg-gray-50/50 dark:bg-zinc-950 p-6 overflow-y-auto">
    <div class="max-w-5xl mx-auto w-full space-y-6">
      <!-- 页面顶部标题 (支持无边框窗口拖拽) -->
      <div class="flex items-center justify-between pb-4 border-b border-gray-200 dark:border-zinc-800 window-drag-region select-none">
        <div class="window-no-drag">
          <h1 class="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            技能库
          </h1>
          <p class="text-xs text-gray-500 dark:text-zinc-400 mt-1">
            智能助手已激活的核心执行与分析能力。
          </p>
        </div>

        <div class="flex items-center gap-2.5 window-no-drag">
          <button
            @click="handleRefresh"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-800 text-xs font-medium text-gray-700 dark:text-zinc-300 transition-colors shadow-2xs cursor-pointer"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': isLoading }" />
            <span>刷新状态</span>
          </button>
        </div>
      </div>

      <!-- 分类技能展示区 -->
      <div class="space-y-6">
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

              <!-- 底部极简提问场景示例 -->
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
    </div>
  </div>
</template>
