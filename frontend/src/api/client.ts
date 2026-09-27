import axios from 'axios'

// 后端 FastAPI 服务的默认基础请求地址
const BASE_URL = 'http://127.0.0.1:8000'

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
})

/**
 * 封装后端所有 RESTful API 的请求客户端集合
 */
export const apiClient = {
  /** 探测后端运行健康状态 */
  async getHealth() {
    const res = await api.get('/health')
    return res.data
  },

  /** 获取系统默认模型与主流供应商预设清单 */
  async getModelConfig() {
    const res = await api.get('/api/models/config')
    return res.data
  },

  /** 获取后端维护的所有大模型服务商配置列表 */
  async getProviders() {
    const res = await api.get('/api/models/providers')
    return res.data
  },

  /** 在线测试大模型 API Key 连通性 */
  async testModel(data: { model: string; base_url: string; api_key: string }) {
    const res = await api.post('/api/models/test', data)
    return res.data
  },

  /** 实时从大模型服务商接口拉取最新模型列表 */
  async fetchModels(data: { base_url: string; api_key?: string }) {
    const res = await api.post('/api/models/fetch', data)
    return res.data
  },

  /** 获取后端所有已注册工具的元数据列表 */
  async getTools() {
    const res = await api.get('/api/tools')
    return res.data.tools
  },

  /** 获取知识库已持久化的文档列表 */
  async getRagDocuments() {
    const res = await api.get('/api/rag/documents')
    return res.data
  },

  /** 上传纯文本片段到向量知识库 */
  async uploadRagText(title: string, content: string) {
    const res = await api.post('/api/rag/upload/text', { title, content })
    return res.data
  },

  /** 上传本地文件到向量知识库进行向量化存储 */
  async uploadRagFile(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/api/rag/upload/file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },

  /** 测试知识库相似度语义检索 */
  async searchRag(query: string, top_k: number = 4) {
    const res = await api.post('/api/rag/search', { query, top_k })
    return res.data
  },

  /** 删除知识库中指定文档及其所属所有向量切片 */
  async deleteRagDocument(doc_id: string) {
    const res = await api.delete(`/api/rag/documents/${doc_id}`)
    return res.data
  },

  /** 一键清空知识库全部数据 */
  async clearRag() {
    const res = await api.post('/api/rag/clear')
    return res.data
  },

  /** 解析上传的文件（包括 PDF、代码、文本文档等），提取文本内容 */
  async parseChatFile(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/api/chat/parse-file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data as {
      name: string
      size: number
      type: string
      is_pdf: boolean
      pages: number
      text: string
    }
  },

  /** 获取指定会话在 LangGraph 检查点中的历史消息记录 */
  async getChatHistory(sessionId: string) {
    const res = await api.get(`/api/chat/history/${sessionId}`)
    return res.data
  },
}
