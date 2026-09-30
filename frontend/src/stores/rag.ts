import { defineStore } from 'pinia'
import { apiClient } from '../api/client'

/**
 * 知识库文档条目接口定义
 */
export interface RagDoc {
  doc_id: string
  title: string
  doc_type: string
  chunks: number
}

/**
 * 知识库 (RAG) Pinia Store：负责文档列表拉取、文件解析上传与相似度检索测试
 */
export const useRagStore = defineStore('rag', {
  state: () => ({
    // 已入库的文档清单
    documents: [] as RagDoc[],
    // 操作加载状态
    isLoading: false,
    // 语义检索结果集
    searchResults: [] as any[],
    // 方案 C 灾备快照状态
    backupStatus: null as null | {
      backup_docs_count: number
      primary_backup_exists: boolean
      primary_backup_path: string
      redundant_backup_exists: boolean
      redundant_backup_path: string
      updated_at?: string | null
    },
  }),

  actions: {
    /** 从后端向量库同步最新文档列表 */
    async fetchDocuments() {
      this.isLoading = true
      try {
        const data = await apiClient.getRagDocuments()
        this.documents = data.documents || []
      } catch (err) {
        console.error('获取知识库文档失败:', err)
      } finally {
        this.isLoading = false
      }
    },

    /** 提交纯文本或 Markdown 笔记切分入库 */
    async uploadText(title: string, content: string) {
      this.isLoading = true
      try {
        const res = await apiClient.uploadRagText(title, content)
        await this.fetchDocuments()
        return {
          success: true,
          message: `笔记《${title}》已成功存入知识库！`,
          data: res,
        }
      } catch (err: any) {
        console.error('上传文本到知识库失败:', err)
        const errMsg = err.response?.data?.detail || err.message || '笔记录入失败'
        return {
          success: false,
          message: errMsg,
        }
      } finally {
        this.isLoading = false
      }
    },

    /** 上传本地文件到知识库并向量化，支持进度回调 */
    async uploadFile(file: File, onProgress?: (percent: number) => void) {
      this.isLoading = true
      try {
        const res = await apiClient.uploadRagFile(file, onProgress)
        await this.fetchDocuments()
        const chunks = res.chunks_count || res.chunks || 0
        return {
          success: true,
          message: `文档《${file.name}》已成功解析并录入知识库（生成 ${chunks} 个切片）`,
          chunks: chunks,
          data: res,
        }
      } catch (err: any) {
        console.error('上传文件到知识库失败:', err)
        const errMsg = err.response?.data?.detail || err.message || '文件上传与解析失败'
        return {
          success: false,
          message: errMsg,
        }
      } finally {
        this.isLoading = false
      }
    },

    /** 删除指定文档的所有向量片段 */
    async deleteDocument(docId: string) {
      try {
        await apiClient.deleteRagDocument(docId)
        this.documents = this.documents.filter(d => d.doc_id !== docId)
        return true
      } catch (err) {
        console.error('删除知识库文档失败:', err)
        return false
      }
    },

    /** 执行向量语义相似度检索测试 */
    async search(query: string, topK: number = 4) {
      try {
        const data = await apiClient.searchRag(query, topK)
        this.searchResults = data.results || []
        return this.searchResults
      } catch (err) {
        console.error('检索知识库失败:', err)
        return []
      }
    },

    /** 【方案 C 灾备】拉取灾备快照状态 */
    async fetchBackupStatus() {
      try {
        this.backupStatus = await apiClient.getRagBackupStatus()
      } catch (err) {
        console.error('获取灾备状态失败:', err)
      }
    },

    /** 【方案 C 灾备】从快照恢复并重建向量库 */
    async restoreBackup() {
      const res = await apiClient.restoreRagBackup()
      await this.fetchDocuments()
      await this.fetchBackupStatus()
      return res
    },

    /** 【方案 C 灾备】导出全量灾备包 */
    async exportBackup() {
      return await apiClient.exportRagBackup()
    },
  },
})
