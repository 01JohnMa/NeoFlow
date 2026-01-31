import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUploadDocument, useProcessDocument, useUploadMultiple, useProcessMerge } from '@/hooks/useDocuments'
import { useCamera } from '@/hooks/useCamera'
import { useProfile } from '@/hooks/useProfile'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
  Plus,
  AlertTriangle,
} from 'lucide-react'

// ============ 上传模式配置（解耦：各租户独立配置）============

// 上传模式类型
type UploadMode = 'lighting_merge' | 'quality_auto' | 'unknown'

// 照明系统固定的文档类型配置（不依赖 API 查询）
const LIGHTING_DOC_TYPES = ['光分布', '积分球']

// 照明系统的模板 ID（用于后端处理）
const LIGHTING_TEMPLATE_ID = 'lighting_combined'

// Merge 模式文件信息
interface MergeFileItem {
  id: string
  file: File | null
  docType: string
  preview: string | null
}

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
  const mergeFileInputRefs = useRef<{ [key: string]: HTMLInputElement | null }>({})
  const uploadMutation = useUploadDocument()
  const processMutation = useProcessDocument()
  const uploadMultipleMutation = useUploadMultiple()
  const processMergeMutation = useProcessMerge()
  const { tenantName, tenantCode, isLoading: profileLoading } = useProfile()

  // ============ 解耦：直接根据 tenantCode 决定上传模式 ============
  const uploadMode: UploadMode = useMemo(() => {
    if (tenantCode === 'lighting') return 'lighting_merge'
    if (tenantCode === 'quality') return 'quality_auto'
    return 'unknown'
  }, [tenantCode])
  const isMobile = useMemo(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(pointer: coarse)').matches
  }, [])
  const fileAccept = isMobile ? 'image/*,application/pdf' : '.pdf,.png,.jpg,.jpeg,.tiff,.bmp'

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [mergeFiles, setMergeFiles] = useState<MergeFileItem[]>([]) // merge 模式多文件
  const [preview, setPreview] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null)

  // ============ 照明系统：直接初始化固定的两文件列表（不依赖 API）============
  useEffect(() => {
    if (uploadMode === 'lighting_merge' && mergeFiles.length === 0) {
      const initialFiles: MergeFileItem[] = LIGHTING_DOC_TYPES.map((docType, index) => ({
        id: `merge-${index}-${Date.now()}`,
        file: null,
        docType,
        preview: null,
      }))
      setMergeFiles(initialFiles)
    }
  }, [uploadMode, mergeFiles.length])

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

  // Handle file selection (single mode)
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

  // Handle merge mode file selection
  const handleMergeFileSelect = useCallback((itemId: string, file: File) => {
    const error = validateFile(file)
    if (error) {
      setUploadError(error)
      return
    }

    setUploadError(null)

    // Generate preview for images
    let filePreview: string | null = null
    if (file.type.startsWith('image/')) {
      const reader = new FileReader()
      reader.onload = (e) => {
        setMergeFiles(prev =>
          prev.map(item =>
            item.id === itemId ? { ...item, preview: e.target?.result as string } : item
          )
        )
      }
      reader.readAsDataURL(file)
    }

    setMergeFiles(prev =>
      prev.map(item =>
        item.id === itemId ? { ...item, file, preview: filePreview } : item
      )
    )
  }, [])

  // Remove merge file
  const removeMergeFile = useCallback((itemId: string) => {
    setMergeFiles(prev =>
      prev.map(item =>
        item.id === itemId ? { ...item, file: null, preview: null } : item
      )
    )
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

  // Upload and process (质量运营：单文件自动识别模式)
  const handleUpload = async () => {
    if (!selectedFile) return

    try {
      setUploadError(null)
      // 质量运营不传 templateId，后端自动识别文档类型
      const result = await uploadMutation.mutateAsync({
        file: selectedFile,
        templateId: undefined
      })
      setUploadedDocId(result.document_id)

      // Start processing (后端会自动识别文档类型并处理)
      await processMutation.mutateAsync({ documentId: result.document_id })

      // Navigate to document detail
      navigate(`/documents/${result.document_id}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : '上传失败'
      setUploadError(message)
    }
  }

  // Upload and process (照明系统：固定两文件合并模式)
  const handleMergeUpload = async () => {
    // 检查是否所有文件都已选择
    const allFilesSelected = mergeFiles.every(item => item.file !== null)
    if (!allFilesSelected) {
      setUploadError('请上传所有必需的文档')
      return
    }

    try {
      setUploadError(null)

      // 1. 上传所有文件（不传 templateId，因为数据库字段是 UUID 类型）
      const filesToUpload = mergeFiles.map(item => ({
        file: item.file!,
        docType: item.docType,
      }))

      const uploadResults = await uploadMultipleMutation.mutateAsync({
        files: filesToUpload,
        // 注意：不传 templateId，避免数据库 UUID 类型错误
      })

      // 2. 调用合并处理（传模板 code，后端会查找真实的 template UUID）
      const mergeResult = await processMergeMutation.mutateAsync({
        templateId: LIGHTING_TEMPLATE_ID,
        files: uploadResults.map(r => ({
          file_path: r.file_path,
          doc_type: r.doc_type,
        })),
      })

      // 3. 跳转到结果页面
      if (mergeResult.document_id) {
        navigate(`/documents/${mergeResult.document_id}`)
      } else {
        // 如果没有返回 document_id，跳转到文档列表
        navigate('/documents')
      }
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
    setMergeFiles([])
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const isUploading = uploadMutation.isPending || processMutation.isPending || 
                      uploadMultipleMutation.isPending || processMergeMutation.isPending
  
  // 检查照明系统合并模式是否可以提交
  const canSubmitMerge = uploadMode === 'lighting_merge' && mergeFiles.length > 0 && mergeFiles.every(item => item.file !== null)

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fadeIn">
      <div>
        <h2 className="text-2xl font-bold text-text-primary">上传文档</h2>
        <p className="text-text-secondary mt-1">
          支持 PDF、PNG、JPG、TIFF、BMP 格式，最大 20MB
        </p>
      </div>

      {/* 未知模式：提示用户选择部门 */}
      {uploadMode === 'unknown' && !profileLoading && (
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

      {/* 照明系统：显示固定的两文件上传模式提示 */}
      {uploadMode === 'lighting_merge' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Layers className="h-5 w-5 text-accent-400" />
              照明综合报告
            </CardTitle>
            <CardDescription>
              {tenantName && `${tenantName} - `}请分别上传积分球和光分布
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Badge variant="outline" className="text-accent-400 border-accent-400">
              合并模式 - 需上传 2 份文档
            </Badge>
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

      {/* Upload Area - 质量运营：单文件自动识别模式 */}
      {!isCameraOpen && !selectedFile && uploadMode === 'quality_auto' && (
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
                accept={fileAccept}
                capture={isMobile ? 'environment' : undefined}
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

      {/* Upload Area - 照明系统：固定两文件合并模式 */}
      {!isCameraOpen && uploadMode === 'lighting_merge' && mergeFiles.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Layers className="h-5 w-5 text-accent-400" />
              上传文档
            </CardTitle>
            <CardDescription>
              请分别上传 {LIGHTING_DOC_TYPES.join(' 和 ')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {mergeFiles.map((item, index) => (
              <div key={item.id} className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Badge variant="outline" className="text-accent-400 border-accent-400">
                    文档 {index + 1}
                  </Badge>
                  <span>{item.docType}</span>
                </Label>
                
                {item.file ? (
                  // 已选择文件
                  <div className="flex items-center gap-4 p-4 rounded-lg bg-bg-secondary border border-border-default">
                    <div className="w-16 h-16 rounded-lg bg-bg-hover flex items-center justify-center overflow-hidden flex-shrink-0">
                      {item.preview ? (
                        <img src={item.preview} alt="预览" className="w-full h-full object-cover" />
                      ) : (
                        <FileText className="h-8 w-8 text-text-muted" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-text-primary truncate">{item.file.name}</p>
                      <p className="text-sm text-text-muted">{formatFileSize(item.file.size)}</p>
                    </div>
                    {!isUploading && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => removeMergeFile(item.id)}
                        className="text-text-muted hover:text-error-500"
                      >
                        <X className="h-5 w-5" />
                      </Button>
                    )}
                  </div>
                ) : (
                  // 未选择文件 - 上传区域
                  <div
                    className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all hover:border-primary-500/50 hover:bg-bg-hover"
                    onClick={() => mergeFileInputRefs.current[item.id]?.click()}
                  >
                    <input
                      ref={(el) => { mergeFileInputRefs.current[item.id] = el }}
                      type="file"
                      accept={fileAccept}
                      capture={isMobile ? 'environment' : undefined}
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) handleMergeFileSelect(item.id, file)
                      }}
                      className="hidden"
                    />
                    <Plus className="h-8 w-8 text-text-muted mx-auto mb-2" />
                    <p className="text-sm text-text-muted">
                      点击选择 {item.docType} 文档
                    </p>
                  </div>
                )}
              </div>
            ))}

            {/* Error */}
            {uploadError && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-error-500/10 border border-error-500/20 text-error-500 text-sm">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            {/* Upload Button */}
            <div className="pt-4 flex gap-3">
              <Button
                className="flex-1"
                onClick={handleMergeUpload}
                disabled={isUploading || !canSubmitMerge}
              >
                {isUploading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    处理中...
                  </>
                ) : (
                  <>
                    <UploadIcon className="h-4 w-4 mr-2" />
                    上传并合并处理
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

      {/* Selected File Preview - 质量运营单文件模式 */}
      {selectedFile && !isCameraOpen && uploadMode === 'quality_auto' && (
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
              {uploadMode === 'quality_auto' ? (
                <span>系统将自动识别文档类型（快递单/检测报告/抽样单）并提取关键信息</span>
              ) : uploadMode === 'lighting_merge' ? (
                <span>请上传积分球和光分布，系统将分别提取后合并结果</span>
              ) : (
                <span>请先选择所属部门</span>
              )}
            </li>
            {uploadMode === 'lighting_merge' && (
              <li className="flex items-start gap-2">
                <Layers className="h-4 w-4 mt-0.5 text-accent-400" />
                <span>合并模式：分别上传积分球和光分布，系统将提取关键参数并生成综合报告</span>
              </li>
            )}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

