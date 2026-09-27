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
        await apiClient.uploadRagText(title, content)
        await this.fetchDocuments()
        return true
      } catch (err) {
        console.error('上传文本到知识库失败:', err)
        return false
      } finally {
        this.isLoading = false
      }
    },

    /** 上传本地文件到知识库并向量化 */
    async uploadFile(file: File) {
      this.isLoading = true
      try {
        await apiClient.uploadRagFile(file)
        await this.fetchDocuments()
        return true
      } catch (err) {
        console.error('上传文件到知识库失败:', err)
        return false
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
  },
})
