import { defineStore } from 'pinia'
import { apiClient } from '../api/client'

/**
 * 动态拉取的模型项格式
 */
export interface FetchedModelItem {
  id: string
  name: string
  owned_by?: string
}

/**
 * 大模型服务商架构
 */
export interface ProviderItem {
  id: string
  name: string
  baseUrl: string
  defaultModel: string
  keyUrl?: string
  needKey: boolean
}

/**
 * 全局设置 Pinia Store：管控大模型连接参数、动态模型拉取、深浅色主题以及系统运行状态
 */
export const useSettingsStore = defineStore('settings', {
  state: () => {
    // 从本地缓存载入各个服务商已拉取的模型清单
    let initialCachedMap: Record<string, FetchedModelItem[]> = {}
    try {
      const stored = localStorage.getItem('agent_cached_models_map')
      if (stored) {
        initialCachedMap = JSON.parse(stored)
      }
    } catch {
      initialCachedMap = {}
    }

    const currentProviderId = localStorage.getItem('agent_current_provider') || 'deepseek'

    return {
      // 当前激活的服务商 ID
      currentProviderId,
      // 当前选定的大语言模型标识
      model: localStorage.getItem(`agent_model_${currentProviderId}`) || localStorage.getItem('agent_model') || 'deepseek-chat',
      // 接口请求基础路径
      baseUrl: localStorage.getItem('agent_base_url') || 'https://api.deepseek.com/v1',
      // 接口访问密钥
      apiKey: localStorage.getItem(`agent_key_${currentProviderId}`) || localStorage.getItem('agent_api_key') || '',
      // 采样温度
      temperature: parseFloat(localStorage.getItem('agent_temp') || '0.7'),
      // 暗黑模式开关状态
      isDark: localStorage.getItem('agent_dark') !== 'false',
      // Python 后端在线状态
      backendOnline: false,
      // 后端端口号
      backendPort: 8000,
      // 知识库检索配置：单次检索参考切片数量
      ragTopK: parseInt(localStorage.getItem('agent_rag_top_k') || '4'),
      // 知识库分块大小（字符数）
      ragChunkSize: parseInt(localStorage.getItem('agent_rag_chunk_size') || '500'),
      // 默认问答模式
      defaultMode: localStorage.getItem('agent_default_mode') || 'react',
      // 操作权限与批准模式：'ask_always' (请求批准) | 'smart' (帮我批准 - 默认) | 'full_access' (完全访问权限)
      approvalMode: (localStorage.getItem('agent_approval_mode') as 'ask_always' | 'smart' | 'full_access') || 'smart',

      // 各个服务商动态拉取并缓存的模型映射表 { providerId: FetchedModelItem[] }
      cachedModelsMap: initialCachedMap,
      // 是否正在从接口动态拉取模型列表
      isFetchingModels: false,
      // 动态拉取错误提示
      fetchModelsError: null as string | null,
      // 动态拉取成功提示
      fetchModelsSuccessMsg: null as string | null,

      // 服务商配置列表（默认预设兜底，优先由后端 /api/models/providers 动态同步）
      providers: [
        {
          id: 'deepseek',
          name: 'DeepSeek',
          baseUrl: 'https://api.deepseek.com/v1',
          defaultModel: 'deepseek-chat',
          keyUrl: 'https://platform.deepseek.com/api_keys',
          needKey: true,
        },
        {
          id: 'openai',
          name: 'OpenAI',
          baseUrl: 'https://api.openai.com/v1',
          defaultModel: 'gpt-4o-mini',
          keyUrl: 'https://platform.openai.com/api-keys',
          needKey: true,
        },
        {
          id: 'qwen',
          name: '通义千问 (Qwen)',
          baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
          defaultModel: 'qwen-plus',
          keyUrl: 'https://dashscope.console.aliyun.com/apiKey',
          needKey: true,
        },
        {
          id: 'moonshot',
          name: '月之暗面 (Kimi)',
          baseUrl: 'https://api.moonshot.cn/v1',
          defaultModel: 'moonshot-v1-8k',
          keyUrl: 'https://platform.moonshot.cn/console/api-keys',
          needKey: true,
        },
        {
          id: 'zhipu',
          name: '智谱清言 (GLM)',
          baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
          defaultModel: 'glm-4-flash',
          keyUrl: 'https://bigmodel.cn/usercenter/apikeys',
          needKey: true,
        },
        {
          id: 'ollama',
          name: 'Ollama (本地离线)',
          baseUrl: 'http://localhost:11434/v1',
          defaultModel: 'llama3.2',
          needKey: false,
        },
        {
          id: 'custom',
          name: '自定义网关',
          baseUrl: localStorage.getItem('agent_custom_base_url') || 'https://api.openai.com/v1',
          defaultModel: localStorage.getItem('agent_custom_model') || 'gpt-4o-mini',
          needKey: true,
        },
      ] as ProviderItem[],
    }
  },

  getters: {
    /** 获取当前选中的服务商对象 */
    currentProvider(state): ProviderItem {
      const found = state.providers.find(p => p.id === state.currentProviderId)
      return found || state.providers[0]
    },

    /** 获取当前服务商已拉取到的最新可用模型列表 */
    currentModels(state): FetchedModelItem[] {
      return state.cachedModelsMap[state.currentProviderId] || []
    },
  },

  actions: {
    /** 从服务端动态同步维护的服务商配置列表 */
    async fetchProviders() {
      try {
        const res = await apiClient.getProviders()
        if (res && Array.isArray(res.providers) && res.providers.length > 0) {
          this.providers = res.providers
          const exists = this.providers.some(p => p.id === this.currentProviderId)
          if (!exists) {
            this.selectProvider(this.providers[0].id)
          }
        }
      } catch (e) {
        console.warn('获取服务端服务商配置列表失败，使用本地预设', e)
      }
    },

    /** 切换供应商 */
    selectProvider(providerId: string) {
      this.currentProviderId = providerId
      const p = this.providers.find(item => item.id === providerId)
      if (p) {
        if (p.id !== 'custom') {
          this.baseUrl = p.baseUrl
        } else {
          this.baseUrl = localStorage.getItem('agent_custom_base_url') || p.baseUrl
        }
        // 恢复该服务商在本地记忆的专属 API Key
        this.apiKey = localStorage.getItem(`agent_key_${providerId}`) || ''
        // 恢复该服务商已选定的模型（如果有），否则回退到默认
        this.model = localStorage.getItem(`agent_model_${providerId}`) || p.defaultModel
      }
      this.fetchModelsError = null
      this.fetchModelsSuccessMsg = null
      this.save()
    },

    /** 更新并记住当前服务商的 API Key */
    setApiKey(key: string) {
      this.apiKey = key
      localStorage.setItem(`agent_key_${this.currentProviderId}`, key)
      this.save()
    },

    /** 更新并记住当前选定的模型标识 */
    setModel(modelId: string) {
      this.model = modelId
      localStorage.setItem(`agent_model_${this.currentProviderId}`, modelId)
      this.save()
    },

    /** 实时从当前大模型服务商接口拉取所有最新可用模型列表 */
    async fetchModels() {
      // 若该供应商需要 Key，且用户尚未输入任何内容，给出直观提醒
      if (this.currentProvider.needKey && !this.apiKey.trim()) {
        this.fetchModelsError = `请先填入您的 ${this.currentProvider.name} API Key，再拉取可用模型列表。`
        return { success: false, error: this.fetchModelsError }
      }

      this.isFetchingModels = true
      this.fetchModelsError = null
      this.fetchModelsSuccessMsg = null

      try {
        const res = await apiClient.fetchModels({
          base_url: this.baseUrl,
          api_key: this.apiKey,
        })

        if (res.success && Array.isArray(res.models) && res.models.length > 0) {
          this.cachedModelsMap[this.currentProviderId] = res.models
          localStorage.setItem('agent_cached_models_map', JSON.stringify(this.cachedModelsMap))
          this.fetchModelsSuccessMsg = `成功获取到 ${res.models.length} 个最新可用模型！`

          // 如果当前模型为空，或当前模型不在已拉取的清单中，自动选中首个可用模型
          const exists = res.models.some((m: FetchedModelItem) => m.id === this.model)
          if (!exists) {
            this.setModel(res.models[0].id)
          }

          return { success: true, count: res.models.length }
        } else {
          const err = res.error || '未能获取到模型列表，请确认 Base URL 与 API Key 是否有效。'
          this.fetchModelsError = err
          return { success: false, error: err }
        }
      } catch (err: any) {
        let msg = err.response?.data?.detail || err.response?.data?.error || err.message || '网络请求异常，请检查接口服务。'
        if (msg === 'Network Error') {
          msg = '无法连接到后端本地服务，请确认后端已正常启动。'
        }
        if (err.response?.status === 404) {
          msg = '后端接口未就绪 (404)，正在重连，请确保 Python 后端已正常启动。'
        }
        this.fetchModelsError = msg
        return { success: false, error: msg }
      } finally {
        this.isFetchingModels = false
      }
    },

    /** 持久化配置到本地存储 */
    save() {
      localStorage.setItem('agent_current_provider', this.currentProviderId)
      localStorage.setItem('agent_model', this.model)
      localStorage.setItem(`agent_model_${this.currentProviderId}`, this.model)
      localStorage.setItem('agent_base_url', this.baseUrl)
      localStorage.setItem('agent_api_key', this.apiKey)
      localStorage.setItem(`agent_key_${this.currentProviderId}`, this.apiKey)
      localStorage.setItem('agent_temp', String(this.temperature))
      localStorage.setItem('agent_dark', String(this.isDark))
      localStorage.setItem('agent_rag_top_k', String(this.ragTopK))
      localStorage.setItem('agent_rag_chunk_size', String(this.ragChunkSize))
      localStorage.setItem('agent_default_mode', this.defaultMode)
      localStorage.setItem('agent_approval_mode', this.approvalMode)
      if (this.currentProviderId === 'custom') {
        localStorage.setItem('agent_custom_base_url', this.baseUrl)
        localStorage.setItem('agent_custom_model', this.model)
      }
    },

    /** 设置操作批准权限模式 */
    setApprovalMode(mode: 'ask_always' | 'smart' | 'full_access') {
      this.approvalMode = mode
      this.save()
    },

    /** 切换暗黑 / 明亮主题 */
    toggleDark() {
      this.isDark = !this.isDark
      this.save()
      if (this.isDark) {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
    },

    /** 定时探活 Python 后端健康状态 */
    async checkBackendHealth() {
      try {
        const res = await apiClient.getHealth()
        this.backendOnline = res.status === 'ok'
      } catch {
        this.backendOnline = false
      }
    },
  },
})
