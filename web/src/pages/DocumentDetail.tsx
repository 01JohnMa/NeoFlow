import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  useDocumentStatus,
  useDeleteDocument,
  useRenameDocument,
} from '@/hooks/useDocuments'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { PageLoader } from '@/components/ui/spinner'
import { Modal } from '@/components/ui/modal'
import { cn, getStatusColor, getStatusText, formatDate } from '@/lib/utils'
import { documentsService } from '@/services/documents'
import { shouldHideDownloadForType } from '@/config/features'
import {
  ArrowLeft,
  Download,
  Trash2,
  X,
  AlertTriangle,
  FileText,
  RefreshCw,
  Pencil,
  Check,
} from 'lucide-react'

function getApiErrorMessage(error: unknown, fallback: string): string {
  const err = error as { response?: { data?: { detail?: string; error?: string } } }
  const detail = err?.response?.data?.detail || err?.response?.data?.error
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

export function DocumentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [isRenaming, setIsRenaming] = useState(false)
  const [newDisplayName, setNewDisplayName] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [modalMessage, setModalMessage] = useState('')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const {
    data: status,
    isLoading: statusLoading,
    isError: statusIsError,
    error: statusError,
    refetch: refetchStatus,
  } = useDocumentStatus(id!, !!id)

  const deleteMutation = useDeleteDocument()
  const renameMutation = useRenameDocument()

  // Delete document
  const handleDelete = async () => {
    if (!id) return
    await deleteMutation.mutateAsync(id)
    navigate('/documents')
  }

  // 开始重命名
  const startRenaming = () => {
    setNewDisplayName(status?.display_name || status?.original_file_name || '')
    setIsRenaming(true)
  }

  // 保存重命名
  const handleRename = async () => {
    if (!id || !newDisplayName.trim()) return
    try {
      await renameMutation.mutateAsync({ documentId: id, displayName: newDisplayName.trim() })
      setIsRenaming(false)
      refetchStatus()
    } catch (err) {
      setModalMessage(getApiErrorMessage(err, '重命名失败，请稍后重试'))
      setIsModalOpen(true)
      console.error('Rename failed:', err)
    }
  }

  // 取消重命名
  const cancelRenaming = () => {
    setIsRenaming(false)
    setNewDisplayName('')
  }

  if (statusLoading) {
    return <PageLoader />
  }

  if (statusIsError) {
    return (
      <div className="mx-auto max-w-xl py-16 text-center">
        <AlertTriangle className="mx-auto mb-4 h-12 w-12 text-error-500" />
        <p className="text-lg font-medium text-text-primary">无法加载文档</p>
        <p className="mt-2 text-sm text-text-muted">
          {getApiErrorMessage(statusError, '文档不存在或暂时无法访问')}
        </p>
        <div className="mt-5 flex justify-center gap-2">
          <Button variant="outline" onClick={() => void refetchStatus()}>重试</Button>
          <Link to="/documents"><Button>返回列表</Button></Link>
        </div>
      </div>
    )
  }

  if (!status) {
    return (
      <div className="text-center py-12">
        <AlertTriangle className="h-12 w-12 text-warning-500 mx-auto mb-4" />
        <p className="text-text-primary text-lg">文档不存在</p>
        <Link to="/documents" className="mt-4 inline-block">
          <Button variant="outline">返回列表</Button>
        </Link>
      </div>
    )
  }

  const isUploaded = status.status === 'uploaded'
  const isQueued = status.status === 'queued'
  const isProcessing = status.status === 'processing'
  const isFailed = status.status === 'failed'
  const hideDownload = shouldHideDownloadForType(status.document_type)

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link to="/documents">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <div className="min-w-0 flex-1">
            {isRenaming ? (
              <div className="flex items-center gap-2">
                <Input
                  value={newDisplayName}
                  onChange={(e) => setNewDisplayName(e.target.value)}
                  className="max-w-xs"
                  placeholder="输入新名称"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleRename()
                    if (e.key === 'Escape') cancelRenaming()
                  }}
                />
                <Button
                  size="icon-sm"
                  onClick={handleRename}
                  disabled={renameMutation.isPending || !newDisplayName.trim()}
                >
                  <Check className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={cancelRenaming}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-text-primary truncate">
                  {status?.display_name || status?.original_file_name || '文档详情'}
                </h2>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={startRenaming}
                  title="重命名"
                >
                  <Pencil className="h-4 w-4" />
                </Button>
              </div>
            )}
            <p className="text-sm text-text-muted truncate">{id}</p>
          </div>
        </div>
        <div className="flex gap-2">
          {!hideDownload && (
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  await documentsService.download(id!)
                } catch (err) {
                  console.error('Download failed:', err)
                }
              }}
            >
              <Download className="h-4 w-4 mr-2" />
              下载
            </Button>
          )}
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setShowDeleteConfirm(true)}
            disabled={deleteMutation.isPending}
          >
            <Trash2 className="h-4 w-4 mr-2" />
            删除
          </Button>
        </div>
      </div>

      {/* Status Card */}
      <Card>
        <CardContent className="pt-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <p className="text-sm text-text-muted">状态</p>
              <Badge className={cn('mt-1', getStatusColor(status.status))}>
                {getStatusText(status.status)}
              </Badge>
            </div>
            <div>
              <p className="text-sm text-text-muted">文档类型</p>
              <p className="mt-1 font-medium text-text-primary">
                {status.document_type || '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-text-muted">上传时间</p>
              <p className="mt-1 text-text-primary">{formatDate(status.created_at)}</p>
            </div>
            <div>
              <p className="text-sm text-text-muted">处理时间</p>
              <p className="mt-1 text-text-primary">
                {status.processed_at ? formatDate(status.processed_at) : '-'}
              </p>
            </div>
          </div>

          {/* 状态补充说明 */}
          {isFailed && status.error_message && (
            <div className="mt-4 p-4 rounded-lg bg-error-500/10 border border-error-500/20">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-error-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-error-500">处理失败</p>
                  <p className="text-sm text-text-secondary mt-1">{status.error_message}</p>
                </div>
              </div>
            </div>
          )}

          {isUploaded && (
            <div className="mt-4 p-4 rounded-lg bg-accent-400/10 border border-accent-400/20">
              <div className="flex items-start gap-3">
                <FileText className="h-5 w-5 text-accent-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-accent-400">文档已上传</p>
                  <p className="text-sm text-text-secondary mt-1">可在 Parse 页面对该文档发起解析。</p>
                </div>
              </div>
            </div>
          )}

          {isQueued && (
            <div className="mt-4 p-4 rounded-lg bg-accent-400/10 border border-accent-400/20">
              <div className="flex items-start gap-3">
                <RefreshCw className="h-5 w-5 text-accent-400 flex-shrink-0 mt-0.5 animate-spin" />
                <div>
                  <p className="font-medium text-accent-400">文档排队中</p>
                  <p className="text-sm text-text-secondary mt-1">当前有其他任务正在执行，系统会自动开始处理，请勿重复提交。</p>
                </div>
              </div>
            </div>
          )}

          {isProcessing && (
            <div className="mt-4 p-4 rounded-lg bg-accent-400/10 border border-accent-400/20">
              <div className="flex items-start gap-3">
                <RefreshCw className="h-5 w-5 text-accent-400 flex-shrink-0 mt-0.5 animate-spin" />
                <div>
                  <p className="font-medium text-accent-400">文档处理中</p>
                  <p className="text-sm text-text-secondary mt-1">高峰期可能需要 2-5 分钟，系统会自动轮询最新状态，请勿重复提交。</p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Modal
        open={isModalOpen}
        title="提示"
        message={modalMessage}
        onClose={() => setIsModalOpen(false)}
      />

      <Modal
        open={showDeleteConfirm}
        title="删除文档"
        message="确定要删除此文档吗？此操作不可恢复。"
        confirmText={deleteMutation.isPending ? '删除中...' : '删除'}
        cancelText="取消"
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDelete}
      />
    </div>
  )
}
