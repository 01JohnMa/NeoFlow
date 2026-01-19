import { useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUploadDocument, useProcessDocument } from '@/hooks/useDocuments'
import { useCamera } from '@/hooks/useCamera'
import { useProfile } from '@/hooks/useProfile'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { cn, formatFileSize } from '@/lib/utils'
import {
  Upload as UploadIcon,
  Camera,
  X,
  FileText,
  Image as ImageIcon,
  CheckCircle,
  AlertCircle,
  Loader2,
  SwitchCamera,
  Aperture,
  Layers,
} from 'lucide-react'

const ACCEPTED_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/tiff',
  'image/bmp',
]
const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20MB

export function Upload() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const uploadMutation = useUploadDocument()
  const processMutation = useProcessDocument()
  const { templates, tenantName, isLoading: profileLoading } = useProfile()

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]) // merge 模式多文件
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('')
  const [preview, setPreview] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null)

  // 获取当前选中的模板
  const selectedTemplate = templates.find(t => t.id === selectedTemplateId)
  const isMergeMode = selectedTemplate?.process_mode === 'merge'

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

  // Validate file
  const validateFile = (file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return '不支持的文件格式，请上传 PDF、PNG、JPG、TIFF 或 BMP 文件'
    }
    if (file.size > MAX_FILE_SIZE) {
      return `文件大小超过限制（最大 ${formatFileSize(MAX_FILE_SIZE)}）`
    }
    return null
  }

  // Handle file selection
  const handleFileSelect = useCallback((file: File) => {
    const error = validateFile(file)
    if (error) {
      setUploadError(error)
      return
    }

    setUploadError(null)
    setSelectedFile(file)
    setUploadedDocId(null)

    // Generate preview for images
    if (file.type.startsWith('image/')) {
      const reader = new FileReader()
      reader.onload = (e) => setPreview(e.target?.result as string)
      reader.readAsDataURL(file)
    } else {
      setPreview(null)
    }
  }, [])

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFileSelect(file)
  }

  // File input change
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFileSelect(file)
  }

  // Camera capture
  const handleCapture = () => {
    const file = capturePhoto()
    if (file) {
      handleFileSelect(file)
      closeCamera()
    }
  }

  // Upload and process
  const handleUpload = async () => {
    if (!selectedFile) return

    try {
      setUploadError(null)
      const result = await uploadMutation.mutateAsync(selectedFile)
      setUploadedDocId(result.document_id)

      // Start processing
      await processMutation.mutateAsync({ documentId: result.document_id })

      // Navigate to document detail
      navigate(`/documents/${result.document_id}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : '上传失败'
      setUploadError(message)
    }
  }

  // Clear selection
  const clearSelection = () => {
    setSelectedFile(null)
    setPreview(null)
    setUploadError(null)
    setUploadedDocId(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const isUploading = uploadMutation.isPending || processMutation.isPending

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fadeIn">
      <div>
        <h2 className="text-2xl font-bold text-text-primary">上传文档</h2>
        <p className="text-text-secondary mt-1">
          支持 PDF、PNG、JPG、TIFF、BMP 格式，最大 20MB
        </p>
      </div>

      {/* 模板选择 */}
      {templates.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Layers className="h-5 w-5 text-primary-400" />
              选择文档类型
            </CardTitle>
            <CardDescription>
              {tenantName && `${tenantName} - `}请选择要处理的文档类型
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <Label htmlFor="template">文档模板</Label>
              <Select
                id="template"
                value={selectedTemplateId}
                onChange={(e) => {
                  setSelectedTemplateId(e.target.value)
                  // 切换模板时清空已选文件
                  clearSelection()
                }}
                disabled={profileLoading}
              >
                <option value="">自动识别文档类型</option>
                {templates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                    {template.process_mode === 'merge' ? ` (需上传${template.required_doc_count}份)` : ''}
                  </option>
                ))}
              </Select>
              {selectedTemplate && (
                <div className="flex items-center gap-2 mt-2">
                  {selectedTemplate.process_mode === 'merge' ? (
                    <Badge variant="outline" className="text-accent-400 border-accent-400">
                      合并模式 - 需上传 {selectedTemplate.required_doc_count} 份文档
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-primary-400 border-primary-400">
                      单文档模式
                    </Badge>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Camera View */}
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

      {/* Upload Area */}
      {!isCameraOpen && !selectedFile && (
        <Card>
          <CardContent className="pt-6">
            <div
              className={cn(
                'border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer',
                dragOver
                  ? 'border-primary-500 bg-primary-500/5'
                  : 'border-border-default hover:border-primary-500/50 hover:bg-bg-hover'
              )}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
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

            {/* Camera Button */}
            {isCameraSupported && (
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

      {/* Selected File Preview */}
      {selectedFile && !isCameraOpen && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">已选择文件</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-start gap-4">
              {/* Preview */}
              <div className="w-24 h-24 rounded-lg bg-bg-secondary flex items-center justify-center overflow-hidden flex-shrink-0">
                {preview ? (
                  <img src={preview} alt="预览" className="w-full h-full object-cover" />
                ) : (
                  <FileText className="h-10 w-10 text-text-muted" />
                )}
              </div>

              {/* File Info */}
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

              {/* Remove Button */}
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

            {/* Error */}
            {uploadError && (
              <div className="mt-4 flex items-center gap-2 p-3 rounded-lg bg-error-500/10 border border-error-500/20 text-error-500 text-sm">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            {/* Upload Button */}
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

      {/* Help Card */}
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
              {selectedTemplate ? (
                <span>
                  已选择 "{selectedTemplate.name}" 模板
                  {isMergeMode && `，需上传 ${selectedTemplate.required_doc_count} 份文档进行合并处理`}
                </span>
              ) : (
                <span>系统将自动识别文档类型并提取关键信息</span>
              )}
            </li>
            {isMergeMode && (
              <li className="flex items-start gap-2">
                <Layers className="h-4 w-4 mt-0.5 text-accent-400" />
                <span>合并模式：分别上传各类文档，系统将分别提取后合并结果</span>
              </li>
            )}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

