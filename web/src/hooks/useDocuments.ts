import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsService } from '@/services/documents'
import { useUploadStore, useAuthStore } from '@/store/useStore'
import type { DocumentStatus } from '@/types'

// Query keys
export const documentKeys = {
  all: ['documents'] as const,
  lists: () => [...documentKeys.all, 'list'] as const,
  list: (filters: Record<string, unknown>) => [...documentKeys.lists(), filters] as const,
  details: () => [...documentKeys.all, 'detail'] as const,
  detail: (id: string) => [...documentKeys.details(), id] as const,
  status: (id: string) => [...documentKeys.all, 'status', id] as const,
  result: (id: string) => [...documentKeys.all, 'result', id] as const,
}

// List documents hook
export function useDocumentList(params: {
  page?: number
  limit?: number
  status?: DocumentStatus
  document_type?: string
} = {}) {
  return useQuery({
    queryKey: documentKeys.list(params),
    queryFn: () => documentsService.list(params),
    staleTime: 30000, // 30 seconds
  })
}

// Single document status hook with polling
export function useDocumentStatus(documentId: string, enabled: boolean = true) {
  return useQuery({
    queryKey: documentKeys.status(documentId),
    queryFn: () => documentsService.getStatus(documentId),
    enabled: enabled && !!documentId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      // Stop polling if completed or failed
      if (status === 'completed' || status === 'failed') {
        return false
      }
      return 2000 // Poll every 2 seconds
    },
  })
}

// Extraction result hook
export function useExtractionResult(documentId: string, enabled: boolean = true) {
  return useQuery({
    queryKey: documentKeys.result(documentId),
    queryFn: () => documentsService.getResult(documentId),
    enabled: enabled && !!documentId,
  })
}

// Upload mutation
export function useUploadDocument() {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const { setUploadProgress, removeUploadProgress } = useUploadStore()

  return useMutation({
    mutationFn: async (file: File) => {
      const tempId = `upload-${Date.now()}`
      setUploadProgress(tempId, 0)

      try {
        const result = await documentsService.upload(
          file,
          user?.id,
          (progress) => setUploadProgress(tempId, progress)
        )
        removeUploadProgress(tempId)
        return result
      } catch (error) {
        removeUploadProgress(tempId)
        throw error
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

// Process document mutation
export function useProcessDocument() {
  const queryClient = useQueryClient()
  const { addProcessingDocument, removeProcessingDocument } = useUploadStore()

  return useMutation({
    mutationFn: async ({ documentId, sync = false }: { documentId: string; sync?: boolean }) => {
      addProcessingDocument(documentId)
      try {
        const result = await documentsService.process(documentId, sync)
        if (!sync) {
          // Don't remove from processing for async - let status polling handle it
        } else {
          removeProcessingDocument(documentId)
        }
        return result
      } catch (error) {
        removeProcessingDocument(documentId)
        throw error
      }
    },
    onSuccess: (_, { documentId }) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.status(documentId) })
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

// Delete document mutation
export function useDeleteDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (documentId: string) => documentsService.delete(documentId),
    onMutate: async (documentId: string) => {
      // 取消正在进行的相关查询，防止覆盖乐观更新
      await queryClient.cancelQueries({ queryKey: documentKeys.lists() })

      // 获取当前所有 list 查询的快照（用于失败时回滚）
      const previousQueries = queryClient.getQueriesData({ queryKey: documentKeys.lists() })

      // 乐观更新：从所有 list 查询缓存中移除该文档
      queryClient.setQueriesData(
        { queryKey: documentKeys.lists() },
        (oldData: { items: Array<{ id: string }>; total: number } | undefined) => {
          if (!oldData) return oldData
          return {
            ...oldData,
            items: oldData.items.filter((doc) => doc.id !== documentId),
            total: Math.max(0, oldData.total - 1),
          }
        }
      )

      // 返回快照，供 onError 回滚使用
      return { previousQueries }
    },
    onError: (_err, _documentId, context) => {
      // 删除失败时，恢复之前的数据
      if (context?.previousQueries) {
        context.previousQueries.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data)
        })
      }
    },
    onSettled: () => {
      // 无论成功还是失败，都重新获取最新数据以确保同步
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

// Validate document mutation
export function useValidateDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      documentId,
      documentType,
      data,
      validationNotes,
    }: {
      documentId: string
      documentType: string
      data: Record<string, unknown>
      validationNotes?: string
    }) => {
      return documentsService.validate(documentId, documentType, data, validationNotes)
    },
    onSuccess: (_, { documentId }) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.result(documentId) })
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

// Reject document mutation
export function useRejectDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ documentId, reason }: { documentId: string; reason: string }) => {
      return documentsService.reject(documentId, reason)
    },
    onSuccess: (_, { documentId }) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.status(documentId) })
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}

// Rename document mutation
export function useRenameDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ documentId, displayName }: { documentId: string; displayName: string }) => {
      return documentsService.rename(documentId, displayName)
    },
    onSuccess: (_, { documentId }) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.status(documentId) })
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
  })
}


