import { useCallback, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProfile } from '@/hooks/useProfile'
import { useUploadDocument, useProcessDocument } from '@/hooks/useDocuments'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { cn, formatFileSize } from '@/lib/utils'
import {
  AlertCircle,
  AlertTriangle,
  FileText,
  Image as ImageIcon,
  Loader2,
  Upload as UploadIcon,
  X,
} from 'lucide-react'

const ACCEPTED_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/tiff',
  'image/bmp',
]
const MAX_FILE_SIZE = 20 * 1024 * 1024

export function Upload() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const uploadMutation = useUploadDocument()
  const processMutation = useProcessDocument()
  const { tenantName, tenantCode, templates, profile, isLoading: profileLoading, fetchProfile, fetchTemplates } = useProfile()

  const availableTemplates = useMemo(
    () => templates.filter(template => template.is_active !== false),
    [templates],
  )

  const [requestedTemplateId, setRequestedTemplateId] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [processError, setProcessError] = useState<string | null>(null)

  const selectedTemplateId = useMemo(() => {
    if (requestedTemplateId && availableTemplates.some(template => template.id === requestedTemplateId)) {
      return requestedTemplateId
    }
    if (availableTemplates.length === 1) {
      return availableTemplates[0].id
    }
    return null
  }, [requestedTemplateId, availableTemplates])

  const validateFile = (file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return '不支持的文件格式，请上传 PDF、PNG、JPG、TIFF 或 BMP 文件'
    }
    if (file.size > MAX_FILE_SIZE) {
      return `文件大小超过限制（最大 ${Math.round(MAX_FILE_SIZE / 1024 / 1024)} MB）`
    }
    return null
  }

  const handleFileSelect = useCallback((file: File) => {
    const error = validateFile(file)
    if (error) {
      setUploadError(error)
      return
    }

    setUploadError(null)
    setSelectedFile(file)

    if (file.type.startsWith('image/')) {
      const reader = new FileReader()
      reader.onload = (event) => setPreview(event.target?.result as string)
      reader.onerror = () => setPreview(null)
      reader.readAsDataURL(file)
    } else {
      setPreview(null)
    }
  }, [])

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (event: React.DragEvent) => {
    event.preventDefault()
    setDragOver(false)
  }

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault()
    setDragOver(false)
    const file = event.dataTransfer.files[0]
    if (file) handleFileSelect(file)
  }

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) handleFileSelect(file)
  }

  const handleUpload = async () => {
    if (!selectedFile || !selectedTemplateId) return

    try {
      setUploadError(null)
      setProcessError(null)
      const result = await uploadMutation.mutateAsync({
        file: selectedFile,
        templateId: selectedTemplateId,
      })
      try { await processMutation.mutateAsync({ documentId: result.document_id }) } catch (error) { setProcessError(error instanceof Error ? error.message : '文档识别失败，请稍后重试'); return }
      navigate(`/documents/${result.document_id}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '文件上传失败，请重试'
      setUploadError(message)
    }
  }

  const clearSelection = () => {
    setSelectedFile(null)
    setPreview(null)
    setUploadError(null)
    setProcessError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const isUploading = uploadMutation.isPending || processMutation.isPending
  const canUpload = Boolean(selectedFile && selectedTemplateId) && !isUploading

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 animate-fadeIn">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary-300">Ingest</p>
        <h2 className="text-3xl font-semibold tracking-tight text-text-primary">上传文档</h2>
        <p className="text-text-secondary mt-1">
          支持 PDF、PNG、JPG、TIFF、BMP 格式，最大 20MB
        </p>
      </div>

      {profileLoading && <Card><CardContent className="py-8 text-center text-text-secondary">正在加载部门与模板信息...</CardContent></Card>}
      {!profileLoading && !profile && <Card className="border-error-500/50"><CardContent className="pt-6"><div className="flex items-center justify-between gap-3 text-error-500"><span>部门信息加载失败，请重试。</span><Button variant="outline" onClick={() => { void fetchProfile(); void fetchTemplates() }}>重新加载</Button></div></CardContent></Card>}
      {!tenantCode && !profileLoading && profile && (
        <Card className="border-warning-500/50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3 text-warning-500">
              <AlertTriangle className="h-6 w-6 flex-shrink-0" />
              <div>
                <p className="font-medium">请先选择所属部门</p>
                <p className="text-sm text-text-muted mt-1">
                  在设置页面选择您的所属部门后，即可使用文档上传功能
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {tenantCode && !profileLoading && availableTemplates.length === 0 && (
        <Card className="border-warning-500/50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3 text-warning-500">
              <AlertTriangle className="h-6 w-6 flex-shrink-0" />
              <div>
                <p className="font-medium">当前部门暂无可用模板</p>
                <p className="text-sm text-text-muted mt-1">
                  请先在后台配置文档模板后再试。
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {tenantCode && availableTemplates.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">选择文档类型</CardTitle>
            <CardDescription>
              {tenantName && `${tenantName} - `}请选择本次上传的文档类型
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {availableTemplates.map(template => (
                <button
                  key={template.id}
                  type="button"
                  onClick={() => setRequestedTemplateId(template.id)}
                  aria-pressed={selectedTemplateId === template.id}
                  disabled={isUploading}
                  className={cn(
                    'px-4 py-2 rounded-lg border text-sm transition-colors',
                    selectedTemplateId === template.id
                      ? 'border-primary-500 bg-primary-500/10 text-primary-400'
                      : 'border-border-default hover:border-primary-500/50 text-text-secondary',
                  )}
                >
                  {template.name}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {tenantCode && selectedTemplateId && !selectedFile && (
        <Card>
          <CardContent className="pt-6">
            <div
              className={cn(
                'border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer',
                dragOver
                  ? 'border-primary-500 bg-primary-500/5'
                  : 'border-border-default hover:border-primary-500/50 hover:bg-bg-hover',
              )}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); fileInputRef.current?.click() } }} role="button" tabIndex={0} aria-label="选择要上传的文档文件">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
                onChange={handleInputChange}
                className="hidden"
              />
              <UploadIcon className="h-12 w-12 text-text-muted mx-auto mb-4" />
              <p className="text-lg font-medium text-text-primary mb-2">
                拖拽文件到此处或点击选择
              </p>
              <p className="text-sm text-text-muted">
                支持 PDF、PNG、JPG、TIFF、BMP 格式
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {selectedFile && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">已选择文件</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-start gap-4">
              <div className="w-24 h-24 rounded-lg bg-bg-secondary flex items-center justify-center overflow-hidden flex-shrink-0">
                {preview ? (
                  <img src={preview} alt="预览" className="w-full h-full object-cover" />
                ) : (
                  <FileText className="h-10 w-10 text-text-muted" />
                )}
              </div>

              <div className="flex-1 min-w-0">
                <p className="font-medium text-text-primary truncate">{selectedFile.name}</p>
                <p className="text-sm text-text-muted mt-1">
                  {formatFileSize(selectedFile.size)}
                </p>
              </div>

              {!isUploading && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={clearSelection}
                  className="text-text-muted hover:text-error-500"
                >
                  <X className="h-5 w-5" />
                </Button>
              )}
            </div>

            {processError && <div role="alert" className="mt-4 p-3 rounded-lg bg-warning-500/10 text-warning-500 text-sm">文件已上传，但识别失败：{processError}</div>}
            {uploadError && (
              <div role="alert" className="mt-4 flex items-center gap-2 p-3 rounded-lg bg-error-500/10 border border-error-500/20 text-error-500 text-sm">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            <div className="mt-6 flex gap-3">
              <Button className="flex-1" onClick={handleUpload} disabled={!canUpload}>
                {isUploading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    上传中...
                  </>
                ) : (
                  <>
                    <UploadIcon className="h-4 w-4 mr-2" />
                    上传并识别
                  </>
                )}
              </Button>
              {!isUploading && (
                <Button variant="outline" onClick={clearSelection}>
                  重新选择
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {!selectedFile && uploadError && (
        <div role="alert" className="flex items-center gap-2 p-3 rounded-lg bg-error-500/10 border border-error-500/20 text-error-500 text-sm">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{uploadError}</span>
        </div>
      )}

      <Card className="bg-bg-secondary/50">
        <CardContent className="pt-6">
          <ul className="space-y-2 text-sm text-text-secondary">
            <li className="flex items-start gap-2">
              <ImageIcon className="h-4 w-4 mt-0.5 text-primary-400" />
              <span>上传清晰的文档图片或PDF文件，确保文字清晰可读</span>
            </li>
            <li className="flex items-start gap-2">
              <ImageIcon className="h-4 w-4 mt-0.5 text-primary-400" />
              <span>移动端可直接拍照上传，建议在良好光线下拍摄</span>
            </li>
            <li className="flex items-start gap-2">
              <FileText className="h-4 w-4 mt-0.5 text-primary-400" />
              <span>
                {tenantCode
                  ? '选择文档类型后上传，系统将自动提取关键信息'
                  : '请先选择所属部门'}
              </span>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
