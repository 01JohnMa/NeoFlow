import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useDocumentList, useDeleteDocument } from '@/hooks/useDocuments'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
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
  const [typeFilter, setTypeFilter] = useState<string>('')
  const limit = 10

  const { data, isLoading, refetch, isFetching } = useDocumentList({
    page,
    limit,
    status: statusFilter as DocumentStatus || undefined,
    document_type: typeFilter || undefined,
  })

  const deleteMutation = useDeleteDocument()

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (confirm('确定要删除此文档吗？')) {
      await deleteMutation.mutateAsync(id)
    }
  }

  const handleDownload = async (id: string, filename: string | undefined, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      await documentsService.download(id, filename)
    } catch (err) {
      console.error('Download failed:', err)
    }
  }

  const totalPages = Math.ceil((data?.total || 0) / limit)

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-text-primary">文档列表</h2>
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
      <Card>
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
              <option value="processing">处理中</option>
              <option value="pending_review">待审核</option>
              <option value="completed">已完成</option>
              <option value="failed">失败</option>
            </Select>
            <Select
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value)
                setPage(1)
              }}
              className="w-36"
            >
              <option value="">全部类型</option>
              <option value="检测报告">检测报告</option>
              <option value="快递单">快递单</option>
              <option value="抽样单">抽样单</option>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Document List */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Spinner />
            </div>
          ) : data?.items.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-text-muted mx-auto mb-4" />
              <p className="text-text-secondary">暂无文档</p>
              <Link to="/upload" className="mt-4 inline-block">
                <Button variant="outline" size="sm">
                  上传第一个文档
                </Button>
              </Link>
            </div>
          ) : (
            <>
              {/* Table Header - Desktop */}
              <div className="hidden md:grid grid-cols-12 gap-4 px-6 py-3 border-b border-border-default bg-bg-secondary/50 text-sm font-medium text-text-muted">
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
    </div>
  )
}


