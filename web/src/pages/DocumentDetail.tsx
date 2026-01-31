import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  useDocumentStatus,
  useExtractionResult,
  useValidateDocument,
  useDeleteDocument,
  useProcessDocument,
  useRenameDocument,
} from '@/hooks/useDocuments'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Spinner, PageLoader } from '@/components/ui/spinner'
import { Modal } from '@/components/ui/modal'
import { cn, getStatusColor, getStatusText, formatDate, getDocumentTypeText } from '@/lib/utils'
import { documentsService } from '@/services/documents'
import { shouldHideDownloadForType } from '@/config/features'
import {
  INSPECTION_REPORT_FIELDS,
  EXPRESS_FIELDS,
  SAMPLING_FORM_FIELDS,
  LIGHTING_REPORT_FIELDS,
  type FieldDefinition,
} from '@/types'
import {
  ArrowLeft,
  Download,
  Trash2,
  Edit,
  Save,
  X,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  FileText,
  Eye,
  Pencil,
  Check,
} from 'lucide-react'

export function DocumentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [isEditing, setIsEditing] = useState(false)
  const [editedData, setEditedData] = useState<Record<string, unknown>>({})
  const [validationNotes, setValidationNotes] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [modalMessage, setModalMessage] = useState('')
  
  // 重命名相关状态
  const [isRenaming, setIsRenaming] = useState(false)
  const [newDisplayName, setNewDisplayName] = useState('')

  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useDocumentStatus(id!, !!id)
  const { data: result, isLoading: resultLoading, refetch: refetchResult } = useExtractionResult(
    id!,
    !!id && (status?.status === 'completed' || status?.status === 'pending_review')
  )

  const validateMutation = useValidateDocument()
  const deleteMutation = useDeleteDocument()
  const processMutation = useProcessDocument()
  const renameMutation = useRenameDocument()

  // Initialize edit data when result loads
  useEffect(() => {
    if (result?.extraction_data) {
      setEditedData(result.extraction_data as unknown as Record<string, unknown>)
    }
  }, [result])

  // Get field definitions based on document type
  const getFields = (): FieldDefinition[] => {
    const type = status?.document_type || result?.document_type
    if (type === '检测报告' || type === 'inspection_report') return INSPECTION_REPORT_FIELDS
    if (type === '快递单' || type === 'express') return EXPRESS_FIELDS
    if (type === '抽样单' || type === 'sampling_form') return SAMPLING_FORM_FIELDS
    if (type === '照明综合报告' || type === 'lighting_combined' || type === 'lighting_report') return LIGHTING_REPORT_FIELDS
    return []
  }

  const fields = getFields()
  const hideDownload = shouldHideDownloadForType(status?.document_type || result?.document_type)

  // Handle field change
  const handleFieldChange = (key: string, value: string) => {
    setEditedData((prev) => ({ ...prev, [key]: value }))
  }

  // Save changes
  const handleSave = async () => {
    // 优先使用 status.document_type，如果为空则使用 result.document_type
    const documentType = status?.document_type || result?.document_type
    if (!id || !documentType) return

    try {
      await validateMutation.mutateAsync({
        documentId: id,
        documentType: documentType,
        data: editedData,
        validationNotes,
      })
      setIsEditing(false)
      refetchResult()
      refetchStatus()  // 刷新状态以更新 document_type
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } }
      const detail = error?.response?.data?.detail
      const message = typeof detail === 'string' && detail.trim()
        ? detail
        : '审核失败，请检查字段后重试'
      setModalMessage(message)
      setIsModalOpen(true)
      console.error('Save failed:', err)
    }
  }

  // Cancel editing
  const handleCancel = () => {
    if (result?.extraction_data) {
      setEditedData(result.extraction_data as unknown as Record<string, unknown>)
    }
    setValidationNotes('')
    setIsEditing(false)
  }

  // Delete document
  const handleDelete = async () => {
    if (!id) return
    if (confirm('确定要删除此文档吗？')) {
      await deleteMutation.mutateAsync(id)
      navigate('/documents')
    }
  }

  // Reprocess document
  const handleReprocess = async () => {
    if (!id) return
    await processMutation.mutateAsync({ documentId: id })
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

  const isProcessing = status.status === 'processing' || processMutation.isPending
  const isPendingReview = status.status === 'pending_review'
  const isCompleted = status.status === 'completed'
  const isFailed = status.status === 'failed'
  // 待审核和已完成状态都可以显示提取结果
  const hasExtractionResult = isPendingReview || isCompleted

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
          {isFailed && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleReprocess}
              disabled={processMutation.isPending}
            >
              <RefreshCw className={cn('h-4 w-4 mr-2', processMutation.isPending && 'animate-spin')} />
              重新处理
            </Button>
          )}
          <Button
            variant="destructive"
            size="sm"
            onClick={handleDelete}
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
                {status.document_type ? getDocumentTypeText(status.document_type) : '-'}
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

          {/* Error Message - 只有状态为 failed 时才显示 */}
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
        </CardContent>
      </Card>

      {/* Processing Status */}
      {isProcessing && (
        <Card>
          <CardContent className="py-12 text-center">
            <Spinner size="lg" className="mx-auto" />
            <p className="mt-4 text-text-primary font-medium">正在处理文档...</p>
            <p className="text-sm text-text-muted mt-1">
              系统正在进行OCR识别和字段提取，请稍候
            </p>
          </CardContent>
        </Card>
      )}

      {/* Extraction Result */}
      {hasExtractionResult && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>提取结果</CardTitle>
              <CardDescription>
                {result?.is_validated ? (
                  <span className="flex items-center gap-1 text-success-500">
                    <CheckCircle className="h-4 w-4" />
                    已审核通过
                  </span>
                ) : (
                  <span className="text-text-muted">等待人工审核</span>
                )}
              </CardDescription>
            </div>
            {!isEditing ? (
              <Button variant="outline" size="sm" onClick={() => setIsEditing(true)}>
                <Edit className="h-4 w-4 mr-2" />
                编辑审核
              </Button>
            ) : (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleSave}
                  loading={validateMutation.isPending}
                >
                  <Save className="h-4 w-4 mr-2" />
                  保存
                </Button>
                <Button variant="outline" size="sm" onClick={handleCancel}>
                  <X className="h-4 w-4 mr-2" />
                  取消
                </Button>
              </div>
            )}
          </CardHeader>
          <CardContent>
            {resultLoading ? (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            ) : fields.length === 0 ? (
              <div className="text-center py-8">
                <FileText className="h-12 w-12 text-text-muted mx-auto mb-4" />
                <p className="text-text-secondary">无法识别的文档类型</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {fields.map((field) => {
                  const value = (editedData[field.key] as string) || ''
                  const originalValue = (result?.extraction_data as unknown as Record<string, unknown>)?.[field.key] as string || ''
                  const isChanged = isEditing && value !== originalValue
                  
                  // 判断是否需要高亮（待审核状态 + 检测报告 + 检验结论字段）
                  const documentType = status?.document_type || result?.document_type
                  const needsHighlight = status?.status === 'pending_review' 
                    && (documentType === '检测报告' || documentType === 'inspection_report')
                    && field.key === 'inspection_conclusion'

                  return (
                    <div key={field.key} className={cn(field.type === 'textarea' && 'md:col-span-2')}>
                      <Label 
                        htmlFor={`field-${field.key}`}
                        className={cn(
                          isChanged && 'text-warning-500',
                          needsHighlight && 'text-orange-500 font-semibold'
                        )}
                      >
                        {field.label}
                        {isChanged && <span className="ml-2 text-xs">(已修改)</span>}
                        {needsHighlight && <span className="ml-2 text-xs animate-pulse">(待审核确认)</span>}
                      </Label>
                      {isEditing ? (
                        field.type === 'textarea' ? (
                          <Textarea
                            id={`field-${field.key}`}
                            value={value}
                            onChange={(e) => handleFieldChange(field.key, e.target.value)}
                            className={cn('mt-1', needsHighlight && 'border-orange-500 border-2')}
                            rows={3}
                          />
                        ) : (
                          <Input
                            id={`field-${field.key}`}
                            type={field.type === 'date' ? 'date' : 'text'}
                            value={value}
                            onChange={(e) => handleFieldChange(field.key, e.target.value)}
                            className={cn('mt-1', isChanged && 'border-warning-500', needsHighlight && 'border-orange-500 border-2')}
                          />
                        )
                      ) : (
                        <p className={cn(
                          'mt-1 p-2 rounded-lg bg-bg-secondary text-text-primary min-h-[40px]',
                          !value && 'text-text-muted italic',
                          needsHighlight && 'border-2 border-orange-500 bg-orange-500/10 font-semibold'
                        )}>
                          {value || '未识别'}
                        </p>
                      )}
                    </div>
                  )
                })}

                {/* Validation Notes */}
                {isEditing && (
                  <div className="md:col-span-2">
                    <Label htmlFor="validation-notes">审核备注</Label>
                    <Textarea
                      id="validation-notes"
                      value={validationNotes}
                      onChange={(e) => setValidationNotes(e.target.value)}
                      placeholder="添加审核备注（可选）"
                      className="mt-1"
                      rows={2}
                    />
                  </div>
                )}
              </div>
            )}

            {/* Confidence Score */}
            {result?.ocr_confidence !== null && result?.ocr_confidence !== undefined && (
              <div className="mt-6 pt-6 border-t border-border-default">
                <p className="text-sm text-text-muted">
                  OCR 置信度: 
                  <span className={cn(
                    'ml-2 font-medium',
                    result.ocr_confidence > 0.8 ? 'text-success-500' :
                    result.ocr_confidence > 0.6 ? 'text-warning-500' : 'text-error-500'
                  )}>
                    {(result.ocr_confidence * 100).toFixed(1)}%
                  </span>
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* OCR Raw Text */}
      {hasExtractionResult && result?.ocr_text && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Eye className="h-5 w-5" />
              OCR 原始文本
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="p-4 rounded-lg bg-bg-secondary text-sm text-text-secondary whitespace-pre-wrap font-mono overflow-x-auto max-h-64 overflow-y-auto">
              {result.ocr_text}
            </pre>
          </CardContent>
        </Card>
      )}

      <Modal
        open={isModalOpen}
        title="审核提示"
        message={modalMessage}
        onClose={() => setIsModalOpen(false)}
      />
    </div>
  )
}


