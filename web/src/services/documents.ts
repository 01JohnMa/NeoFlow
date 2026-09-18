import api from './api'
import type {
  Document,
  UploadResponse,
  DocumentListResponse,
} from '@/types'

export const documentsService = {
  // Upload document
  async upload(
    file: File,
    options?: {
      onProgress?: (progress: number) => void
    }
  ): Promise<UploadResponse> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.post<UploadResponse>('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && options?.onProgress) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          options.onProgress(progress)
        }
      },
    })
    return response.data
  },

  // Get document status
  async getStatus(documentId: string): Promise<{
    document_id: string
    status: string
    document_type: string | null
    display_name: string | null
    original_file_name: string | null
    error_message: string | null
    created_at: string
    updated_at: string
    processed_at: string | null
  }> {
    const response = await api.get(`/documents/${documentId}/status`)
    return response.data
  },

  // List documents
  async list(params: {
    page?: number
    limit?: number
    status?: string
    document_type?: string
  } = {}): Promise<DocumentListResponse> {
    const response = await api.get<DocumentListResponse>('/documents/', { params })
    return response.data
  },

  // Get single document
  async get(documentId: string): Promise<Document> {
    const response = await api.get<Document>(`/documents/${documentId}`)
    return response.data
  },

  // Delete document
  async delete(documentId: string): Promise<{ document_id: string; message: string }> {
    const response = await api.delete(`/documents/${documentId}`)
    return response.data
  },

  // Fetch raw document blob (with auth token), for in-page preview
  async fetchFileBlob(documentId: string): Promise<Blob> {
    const response = await api.get(`/documents/${documentId}/download`, {
      responseType: 'blob',
    })
    return response.data
  },

  // Download document (with auth token)
  async download(documentId: string, filename?: string): Promise<void> {
    const response = await api.get(`/documents/${documentId}/download`, {
      responseType: 'blob',
    })
    
    // 从响应头获取文件名，或使用传入的文件名
    const contentDisposition = response.headers['content-disposition']
    let downloadFilename = filename || 'document'
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)["']?/i)
      if (filenameMatch) {
        downloadFilename = decodeURIComponent(filenameMatch[1])
      }
    }
    
    // 创建 Blob URL 并触发下载
    const blob = new Blob([response.data])
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = downloadFilename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  },

  // Rename document
  async rename(
    documentId: string,
    displayName: string
  ): Promise<{ success: boolean; message: string; display_name: string }> {
    const response = await api.put(`/documents/${documentId}/rename`, {
      display_name: displayName,
    })
    return response.data
  },
}

export default documentsService
