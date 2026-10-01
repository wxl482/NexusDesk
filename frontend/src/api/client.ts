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

  /** 获取系统完整诊断数据 */
  async getDiagnostics() {
    const res = await api.get('/api/system/diagnostics')
    return res.data
  },

  /** 导出系统诊断数据包文件 */
  async exportDiagnostics() {
    const res = await api.get('/api/system/diagnostics/export', { responseType: 'blob' })
    return res
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

  /** 上传本地文件到向量知识库进行向量化存储，支持上传进度回调 */
  async uploadRagFile(file: File, onProgress?: (percent: number) => void) {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/api/rag/upload/file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          onProgress(percent)
        }
      },
    })
    return res.data
  },

  /** 上传本地文件到向量知识库，通过 SSE 实时流式接收真实分块与多批次向量化进度 */
  async uploadRagFileStream(
    file: File,
    onProgressEvent: (event: {
      stage: string
      progress: number
      message: string
      chunks_count?: number
      parent_chunks_count?: number
      chunks?: number
      parent_chunks?: number
      success?: boolean
    }) => void
  ) {
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${BASE_URL}/api/rag/upload/file/stream`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      throw new Error(`文件上传请求失败: HTTP ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('当前运行环境不支持 ReadableStream')

    const decoder = new TextDecoder()
    let buffer = ''
    let lastEvent: any = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data:')) {
          try {
            const dataStr = trimmed.slice(5).trim()
            if (dataStr) {
              const eventObj = JSON.parse(dataStr)
              lastEvent = eventObj
              onProgressEvent(eventObj)
            }
          } catch (e) {
            console.error('解析 SSE 流数据失败:', line, e)
          }
        }
      }
    }

    return lastEvent
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

  /** 【方案 C 灾备】获取知识库灾备快照状态与文档数量 */
  async getRagBackupStatus() {
    const res = await api.get('/api/rag/backup/status')
    return res.data as {
      success: boolean
      backup_docs_count: number
      primary_backup_exists: boolean
      primary_backup_path: string
      redundant_backup_exists: boolean
      redundant_backup_path: string
      updated_at?: string | null
    }
  },

  /** 【方案 C 灾备】从灾备快照恢复并重建 Milvus 向量库 */
  async restoreRagBackup() {
    const res = await api.post('/api/rag/backup/restore')
    return res.data as { success: boolean; recovered_chunks: number; message: string }
  },

  /** 【方案 C 灾备】导出知识库全量灾备包 */
  async exportRagBackup() {
    const res = await api.post('/api/rag/backup/export')
    return res.data as { success: boolean; exported_file: string; message: string }
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

  /** 获取所有已配置的 MCP 服务列表 */
  async getMcpServers() {
    const res = await api.get('/api/mcp/servers')
    return res.data.servers
  },

  /** 注册或更新 MCP 外部协议服务 */
  async registerMcpServer(data: {
    id: string
    name: string
    command: string
    args?: string[]
    env?: Record<string, string>
    enabled?: boolean
    description?: string
  }) {
    const res = await api.post('/api/mcp/servers', data)
    return res.data
  },

  /** 切换 MCP 服务启用/停用状态 */
  async toggleMcpServer(serverId: string, enabled: boolean) {
    const res = await api.post(`/api/mcp/servers/${serverId}/toggle`, { enabled })
    return res.data
  },

  /** 探测 MCP 服务可用工具 (stdio 实时握手) */
  async probeMcpServer(serverId: string) {
    const res = await api.post(`/api/mcp/servers/${serverId}/probe`)
    return res.data
  },

  /** 删除 MCP 服务 */
  async deleteMcpServer(serverId: string) {
    const res = await api.delete(`/api/mcp/servers/${serverId}`)
    return res.data
  },

  /** 获取所有 MCP 汇集激活的工具列表 */
  async getMcpTools() {
    const res = await api.get('/api/mcp/tools')
    return res.data.tools
  },
}
