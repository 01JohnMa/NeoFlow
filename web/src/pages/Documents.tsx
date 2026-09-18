import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useDocumentList, useDeleteDocument, documentKeys } from '@/hooks/useDocuments'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Modal } from '@/components/ui/modal'
import { cn, getStatusColor, getStatusText, formatDate, formatFileSize } from '@/lib/utils'
import { shouldHideDownloadForType } from '@/config/features'
import type { DocumentStatus } from '@/types'
import {
  FileText,
  Trash2,
  Download,
  Filter,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
} from 'lucide-react'
import { documentsService } from '@/services/documents'

export function Documents() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const limit = 10

  const { data, isLoading, isError, error, refetch, isFetching } = useDocumentList({
    page,
    limit,
    status: statusFilter as DocumentStatus || undefined,
  })

  const deleteMutation = useDeleteDocument()
  const queryClient = useQueryClient()

  // 悬停时预取详情数据，点击进入详情页不再等第一跳
  const prefetchDocument = (doc: { id: string }) => {
    void queryClient.prefetchQuery({
      queryKey: documentKeys.status(doc.id),
      queryFn: () => documentsService.getStatus(doc.id),
    })
  }

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDeleteTargetId(id)
  }

  const confirmDelete = async () => {
    if (!deleteTargetId) return
    await deleteMutation.mutateAsync(deleteTargetId)
    setDeleteTargetId(null)
  }

  const handleDownload = async (id: string, filename: string | undefined, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      setDownloadError(null)
      await documentsService.download(id, filename)
    } catch (err) {
      console.error('Download failed:', err)
      setDownloadError('下载失败，请稍后重试。')
    }
  }

  const totalPages = Math.ceil((data?.total || 0) / limit)

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary-300">Library</p>
          <h2 className="text-3xl font-semibold tracking-tight text-text-primary">文档列表</h2>
          <p className="text-text-secondary mt-1">
            共 {data?.total || 0} 个文档
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
          </Button>
          <Link to="/upload">
            <Button>上传文档</Button>
          </Link>
        </div>
      </div>

      {/* Filters */}
      <Card className="overflow-hidden">
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-text-muted" />
              <span className="text-sm text-text-secondary">筛选:</span>
            </div>
            <Select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                setPage(1)
              }}
              className="w-36"
            >
              <option value="">全部状态</option>
              <option value="pending">待处理</option>
              <option value="uploaded">已上传</option>
              <option value="queued">排队中</option>
              <option value="processing">处理中</option>
              <option value="completed">已完成</option>
              <option value="failed">失败</option>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Document List */}
      {downloadError && (
        <div role="alert" className="flex items-center justify-between rounded-xl border border-error-500/30 bg-error-500/10 px-4 py-3 text-sm text-error-200">
          <span>{downloadError}</span>
          <Button variant="ghost" size="sm" onClick={() => setDownloadError(null)}>知道了</Button>
        </div>
      )}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Spinner />
            </div>
          ) : isError ? (
            <div className="py-12 text-center">
              <p className="text-text-secondary">文档加载失败{error instanceof Error && error.message ? `：${error.message}` : ''}</p>
              <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()} disabled={isFetching}>
                <RefreshCw className={cn('mr-2 h-4 w-4', isFetching && 'animate-spin')} />重试
              </Button>
            </div>
          ) : data?.items.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-text-muted mx-auto mb-4" />
              {statusFilter ? (
                <>
                  <p className="text-text-secondary">没有符合当前筛选条件的文档</p>
                  <Button variant="outline" size="sm" className="mt-4" onClick={() => { setStatusFilter(''); setPage(1) }}>清除筛选</Button>
                </>
              ) : (
                <>
                  <p className="text-text-secondary">暂无文档</p>
                  <Link to="/upload" className="mt-4 inline-block"><Button variant="outline" size="sm">上传第一个文档</Button></Link>
                </>
              )}
            </div>
          ) : (
            <>
              {/* Table Header - Desktop */}
              <div className="hidden md:grid grid-cols-12 gap-4 border-b border-border-default bg-bg-secondary/70 px-6 py-3 text-xs font-semibold uppercase tracking-wide text-text-muted">
                <div className="col-span-4">文件名</div>
                <div className="col-span-2">类型</div>
                <div className="col-span-2">状态</div>
                <div className="col-span-2">上传时间</div>
                <div className="col-span-2 text-right">操作</div>
              </div>

              {/* Table Body */}
              <div className="divide-y divide-border-default">
                {data?.items.map((doc) => {
                  const hideDownload = shouldHideDownloadForType(doc.document_type)
                  return (
                    <Link
                      key={doc.id}
                      to={`/documents/${doc.id}`}
                      onMouseEnter={() => prefetchDocument(doc)}
                      className="block hover:bg-bg-hover transition-colors cursor-pointer"
                    >
                    <div className="grid grid-cols-1 md:grid-cols-12 gap-4 px-6 py-4 items-center">
                      {/* File Name */}
                      <div className="md:col-span-4 flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-primary-500/10 flex items-center justify-center flex-shrink-0">
                          <FileText className="h-5 w-5 text-primary-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-medium text-text-primary truncate">
                            {doc.display_name || doc.original_file_name || doc.file_name}
                          </p>
                          <p className="text-xs text-text-muted md:hidden">
                            {formatFileSize(doc.file_size || 0)} · {formatDate(doc.created_at)}
                          </p>
                        </div>
                      </div>

                      {/* Type */}
                      <div className="md:col-span-2 hidden md:block">
                        {doc.document_type ? (
                          <Badge variant="secondary">{doc.document_type}</Badge>
                        ) : (
                          <span className="text-text-muted text-sm">-</span>
                        )}
                      </div>

                      {/* Status */}
                      <div className="md:col-span-2">
                        <Badge className={getStatusColor(doc.status)}>
                          {getStatusText(doc.status)}
                        </Badge>
                        {doc.document_type && (
                          <Badge variant="secondary" className="md:hidden ml-2">
                            {doc.document_type}
                          </Badge>
                        )}
                      </div>

                      {/* Time */}
                      <div className="md:col-span-2 hidden md:block text-sm text-text-secondary">
                        {formatDate(doc.created_at)}
                      </div>

                      {/* Actions */}
                      <div className="md:col-span-2 flex justify-end gap-1">
                        {!hideDownload && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={(e) => handleDownload(doc.id, doc.original_file_name || doc.file_name, e)}
                            title="下载"
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={(e) => handleDelete(doc.id, e)}
                          className="text-error-500 hover:text-error-500"
                          title="删除"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </Link>
                  )
                })}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-text-muted">
            第 {page} 页，共 {totalPages} 页
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              <ChevronLeft className="h-4 w-4" />
              上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
            >
              下一页
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <Modal
        open={!!deleteTargetId}
        title="删除文档"
        message="确定要删除此文档吗？此操作不可恢复。"
        confirmText={deleteMutation.isPending ? '删除中...' : '删除'}
        cancelText="取消"
        onClose={() => setDeleteTargetId(null)}
        onConfirm={confirmDelete}
      />
    </div>
  )
}
