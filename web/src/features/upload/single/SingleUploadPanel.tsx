import { useCallback, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUploadDocument, useProcessDocument } from '@/hooks/useDocuments'
import { useCamera } from '@/hooks/useCamera'
import type { Template } from '@/store/useStore'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn, formatFileSize } from '@/lib/utils'
import { resolveSelectedSingleTemplateId } from '@/features/upload/single/singleUploadState'
import {
  AlertCircle,
  Aperture,
  Camera,
  CheckCircle,
  FileText,
  Image as ImageIcon,
  Loader2,
  SwitchCamera,
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

function stripExtension(filename: string): string {
  return filename.replace(/\.[^.]+$/, '')
}

function resolveEffectivePushName(customName: string, fallbackName: string): string {
  return customName.trim() || fallbackName.trim()
}

function getDefaultSinglePushName(file: File | null): string {
  if (!file) return ''
  return stripExtension(file.name)
}

interface SingleUploadPanelProps {
  tenantName?: string | null
  templates: Template[]
}

export function SingleUploadPanel({ tenantName, templates }: SingleUploadPanelProps) {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const uploadMutation = useUploadDocument()
  const processMutation = useProcessDocument()
  const singleTemplates = useMemo(
    () => templates.filter(template => template.is_active !== false),
    [templates],
  )
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null)
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null)
  const [singleCustomPushName, setSingleCustomPushName] = useState('')
  const isMobile = useMemo(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(pointer: coarse)').matches
  }, [])
  const fileAccept = isMobile ? 'image/*,application/pdf' : '.pdf,.png,.jpg,.jpeg,.tiff,.bmp'

  const {
    isOpen: isCameraOpen,
    isSupported: isCameraSupported,
    error: cameraError,
    setVideoRef,
    openCamera,
    closeCamera,
    capturePhoto,
    switchCamera,
  } = useCamera()

  const effectiveSelectedTemplateId = useMemo(
    () => resolveSelectedSingleTemplateId(singleTemplates, selectedTemplateId),
    [selectedTemplateId, singleTemplates],
  )

  const validateFile = (file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return '不支持的文件格式，请上传 PDF、PNG、JPG、TIFF 或 BMP 文件'
    }
    if (file.size > MAX_FILE_SIZE) {
      return `文件大小超过限制（最大 ${formatFileSize(MAX_FILE_SIZE)}）`
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
    setUploadedDocId(null)

    if (file.type.startsWith('image/')) {
      const reader = new FileReader()
      reader.onload = (event) => setPreview(event.target?.result as string)
      reader.readAsDataURL(file)
    } else {
      setPreview(null)
    }
  }, [])

  const handleCapture = () => {
    const file = capturePhoto()
    if (file) {
      handleFileSelect(file)
      closeCamera()
    }
  }

  const handleUpload = async () => {
    if (!selectedFile) return

    if (singleTemplates.length > 1 && !effectiveSelectedTemplateId) {
      setUploadError('请先选择文档类型后再上传')
      return
    }

    try {
      setUploadError(null)
      const result = await uploadMutation.mutateAsync({
        file: selectedFile,
        templateId: effectiveSelectedTemplateId || undefined,
        customPushName: resolveEffectivePushName(singleCustomPushName, singleRecommendedPushName) || undefined,
      })
      setUploadedDocId(result.document_id)
      await processMutation.mutateAsync({ documentId: result.document_id })
      navigate(`/documents/${result.document_id}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '上传失败'
      setUploadError(message)
    }
  }

  const clearSelection = () => {
    setSelectedFile(null)
    setPreview(null)
    setUploadError(null)
    setUploadedDocId(null)
    setSingleCustomPushName('')
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const singleRecommendedPushName = getDefaultSinglePushName(selectedFile)
  const isUploading = uploadMutation.isPending || processMutation.isPending

  return (
    <div className="space-y-6">
      {singleTemplates.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">选择文档类型</CardTitle>
            <CardDescription>
              {tenantName && `${tenantName} - `}请选择本次上传的文档类型
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {singleTemplates.map(template => (
                <button
                  key={template.id}
                  onClick={() => setSelectedTemplateId(template.id)}
                  className={cn(
                    'px-4 py-2 rounded-lg border text-sm transition-colors',
                    effectiveSelectedTemplateId === template.id
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

      {isCameraOpen && (
        <Card className="overflow-hidden">
          <CardContent className="p-0 relative">
            <video
              ref={setVideoRef}
              autoPlay
              playsInline
              muted
              webkit-playsinline="true"
              className="w-full aspect-[4/3] object-cover bg-black"
            />
            <div className="absolute bottom-4 left-0 right-0 flex justify-center gap-4">
              <Button variant="secondary" size="icon" onClick={switchCamera}>
                <SwitchCamera className="h-5 w-5" />
              </Button>
              <Button
                size="lg"
                className="h-16 w-16 rounded-full"
                onClick={handleCapture}
              >
                <Aperture className="h-8 w-8" />
              </Button>
              <Button variant="secondary" size="icon" onClick={closeCamera}>
                <X className="h-5 w-5" />
              </Button>
            </div>
            {cameraError && (
              <div className="absolute top-4 left-4 right-4 p-3 rounded-lg bg-error-500/90 text-white text-sm">
                {cameraError}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {!isCameraOpen && !selectedFile && !effectiveSelectedTemplateId && singleTemplates.length > 1 && (
        <Card>
          <CardContent className="pt-6">
            <div className="rounded-xl border border-dashed border-border-default p-8 text-center text-sm text-text-muted">
              请先选择文档类型，再上传文件。
            </div>
          </CardContent>
        </Card>
      )}

      {!isCameraOpen && !selectedFile && effectiveSelectedTemplateId && (
        <Card>
          <CardContent className="pt-6">
            <div
              className={cn(
                'border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer',
                dragOver
                  ? 'border-primary-500 bg-primary-500/5'
                  : 'border-border-default hover:border-primary-500/50 hover:bg-bg-hover',
              )}
              onDragOver={(event) => {
                event.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={(event) => {
                event.preventDefault()
                setDragOver(false)
              }}
              onDrop={(event) => {
                event.preventDefault()
                setDragOver(false)
                const file = event.dataTransfer.files[0]
                if (file) handleFileSelect(file)
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={fileAccept}
                capture={isMobile ? 'environment' : undefined}
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) handleFileSelect(file)
                }}
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

            {!isMobile && isCameraSupported && (
              <div className="mt-6 text-center">
                <p className="text-sm text-text-muted mb-3">或者使用相机拍照</p>
                <Button variant="outline" onClick={openCamera} className="gap-2">
                  <Camera className="h-4 w-4" />
                  打开相机
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {selectedFile && !isCameraOpen && (
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
                {uploadedDocId && (
                  <div className="flex items-center gap-2 mt-2 text-success-500">
                    <CheckCircle className="h-4 w-4" />
                    <span className="text-sm">已上传，正在处理...</span>
                  </div>
                )}
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

            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <Label className="text-sm text-text-secondary">
                  飞书推送文件名（可选）
                </Label>
                {!isUploading && singleRecommendedPushName && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs text-text-muted"
                    onClick={() => setSingleCustomPushName(singleRecommendedPushName)}
                  >
                    使用推荐文件名
                  </Button>
                )}
              </div>
              <Input
                value={singleCustomPushName}
                onChange={event => setSingleCustomPushName(event.target.value)}
                placeholder={singleRecommendedPushName || '请输入飞书推送文件名'}
                maxLength={100}
                disabled={isUploading}
                className="text-sm"
              />
              <div className="rounded-md bg-bg-secondary px-3 py-2 text-xs text-text-muted">
                实际生效名称：{resolveEffectivePushName(singleCustomPushName, singleRecommendedPushName) || '未生成'}
              </div>
            </div>

            {uploadError && (
              <div className="mt-4 flex items-center gap-2 p-3 rounded-lg bg-error-500/10 border border-error-500/20 text-error-500 text-sm">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            <div className="mt-6 flex gap-3">
              <Button
                className="flex-1"
                onClick={handleUpload}
                disabled={isUploading}
              >
                {isUploading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    处理中...
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

      <Card className="bg-bg-secondary/50">
        <CardHeader>
          <CardTitle className="text-base">使用说明</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm text-text-secondary">
            <li className="flex items-start gap-2">
              <ImageIcon className="h-4 w-4 mt-0.5 text-primary-400" />
              <span>上传清晰的文档图片或PDF文件，确保文字清晰可读</span>
            </li>
            <li className="flex items-start gap-2">
              <Camera className="h-4 w-4 mt-0.5 text-primary-400" />
              <span>移动端可直接使用相机拍照，建议在良好光线下拍摄</span>
            </li>
            <li className="flex items-start gap-2">
              <FileText className="h-4 w-4 mt-0.5 text-primary-400" />
              <span>选择文档类型后上传，系统将自动提取关键信息</span>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
