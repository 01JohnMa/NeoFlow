import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUploadDocument, useProcessDocument, useUploadMultiple } from '@/hooks/useDocuments'
import documentsService from '@/services/documents'
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

// ============ 上传模式配置（数据驱动：根据模板数据自动判断）============

// 上传模式类型：merge=合并多文件模式，single=单文件手动选模板模式
type UploadMode = 'merge' | 'single' | 'unknown'

// 照明合并进度阶段
type MergePhase = 'idle' | 'uploading' | 'processing'

// merge 模式回退模板 ID（当 mergeRules 尚未加载时使用）
const LIGHTING_TEMPLATE_ID = 'integrating_sphere'

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
  const { tenantName, tenantCode, mergeRules, templates, isLoading: profileLoading } = useProfile()

  // ============ 数据驱动：根据模板数据自动判断上传模式 ============
  // merge 规则存在 → merge 模式；有 single 模板 → single 模式；无部门 → unknown
  const uploadMode: UploadMode = useMemo(() => {
    if (!tenantCode) return 'unknown'
    if (mergeRules.length > 0) return 'merge'
    if (templates.some(t => t.process_mode === 'single')) return 'single'
    return 'unknown'
  }, [tenantCode, mergeRules, templates])

  // single 模式可用的模板列表
  const singleTemplates = useMemo(
    () => templates.filter(t => t.process_mode === 'single'),
    [templates]
  )

  // merge 模式的两种文档类型（从 mergeRules 派生，不再硬编码）
  const mergeDocTypes = useMemo(() => {
    if (mergeRules.length === 0) return ['积分球', '光分布'] // 回退值
    return [mergeRules[0].doc_type_a, mergeRules[0].doc_type_b]
  }, [mergeRules])

  // 优先使用后端返回的 merge 模板 ID，避免前端硬编码导致配置不生效
  const lightingMergeTemplateId = useMemo(() => {
    const mergeTemplateIds = new Set(mergeRules.map((rule) => rule.template_id))
    const firstMergeTemplate = templates.find(
      (template) => template.process_mode === 'merge' && mergeTemplateIds.has(template.id)
    )
    return firstMergeTemplate?.id || mergeRules[0]?.template_id || LIGHTING_TEMPLATE_ID
  }, [mergeRules, templates])
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
  // single 模式：用户选中的模板 ID（单模板时自动选中）
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null)

  // ============ 照明合并进度 ============
  const [mergePhase, setMergePhase] = useState<MergePhase>('idle')
  const [mergeProgress, setMergeProgress] = useState(0)
  const mergeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopMergeTimer = useCallback(() => {
    if (mergeTimerRef.current) {
      clearInterval(mergeTimerRef.current)
      mergeTimerRef.current = null
    }
  }, [])

  // single 模式：只有一个模板时自动选中
  useEffect(() => {
    if (uploadMode === 'single' && singleTemplates.length === 1) {
      setSelectedTemplateId(singleTemplates[0].id)
    }
  }, [uploadMode, singleTemplates])

  // merge 模式：根据 mergeDocTypes 初始化文件列表
  useEffect(() => {
    if (uploadMode === 'merge' && mergeFiles.length === 0 && mergeDocTypes.length > 0) {
      const initialFiles: MergeFileItem[] = mergeDocTypes.map((docType, index) => ({
        id: `merge-${index}-${Date.now()}`,
        file: null,
        docType,
        preview: null,
      }))
      setMergeFiles(initialFiles)
    }
  }, [uploadMode, mergeFiles.length, mergeDocTypes])

  // 组件卸载时清理定时器
  useEffect(() => {
    return () => { stopMergeTimer() }
  }, [])

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

  // Upload and process (single 模式：用户手动选模板)
  const handleUpload = async () => {
    if (!selectedFile) return

    try {
      setUploadError(null)
      const result = await uploadMutation.mutateAsync({
        file: selectedFile,
        templateId: selectedTemplateId || undefined
      })
      setUploadedDocId(result.document_id)

      await processMutation.mutateAsync({ documentId: result.document_id })

      navigate(`/documents/${result.document_id}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : '上传失败'
      setUploadError(message)
    }
  }

  // Upload and process (照明系统：固定两文件合并模式)
  const handleMergeUpload = async () => {
    // 至少选择一个文件即可提交
    const hasAtLeastOneFile = mergeFiles.some(item => item.file !== null)
    if (!hasAtLeastOneFile) {
      setUploadError('请至少上传一个文档')
      return
    }

    setUploadError(null)
    setMergePhase('uploading')
    setMergeProgress(0)
    stopMergeTimer()

    try {
      // 1. 上传所有文件，实时反映上传进度（占总进度 0–20%）
      const filesToUpload = mergeFiles
        .filter(item => item.file !== null)
        .map(item => ({
          file: item.file!,
          docType: item.docType,
        }))

      const uploadResults = await uploadMultipleMutation.mutateAsync({
        files: filesToUpload,
        onProgress: (p) => setMergeProgress(Math.round(p * 0.2)),
      })

      // 2. 提交合并任务（立即返回 job_id，后台处理）
      setMergePhase('processing')
      setMergeProgress(20)
      const { job_id } = await documentsService.submitMergeJob(
        lightingMergeTemplateId,
        uploadResults.map(r => ({ file_path: r.file_path, doc_type: r.doc_type })),
      )

      // 3. 轮询任务状态，根据后端真实阶段更新进度条
      await new Promise<void>((resolve, reject) => {
        mergeTimerRef.current = setInterval(async () => {
          try {
            const jobStatus = await documentsService.getJobStatus(job_id)
            // 进度：后端值在 20~100 区间内展示
            setMergeProgress(Math.max(20, jobStatus.progress))

            if (jobStatus.status === 'completed') {
              stopMergeTimer()
              setMergeProgress(100)
              await new Promise(r => setTimeout(r, 600))
              const firstDocId = jobStatus.document_ids?.[0]
              if (firstDocId) {
                navigate(`/documents/${firstDocId}`)
              } else {
                navigate('/documents')
              }
              resolve()
            } else if (jobStatus.status === 'failed') {
              stopMergeTimer()
              reject(new Error(jobStatus.error || '处理失败'))
            }
          } catch {
            // 单次轮询失败不中断，继续等待
          }
        }, 3000)
      })
    } catch (err) {
      stopMergeTimer()
      setMergePhase('idle')
      setMergeProgress(0)
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
    stopMergeTimer()
    setMergePhase('idle')
    setMergeProgress(0)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const isUploading = uploadMutation.isPending || processMutation.isPending ||
                      uploadMultipleMutation.isPending
  
  // 检查合并模式是否可以提交
  const canSubmitMerge = uploadMode === 'merge' && mergeFiles.length > 0 && mergeFiles.some(item => item.file !== null)

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fadeIn">
      <div>
        <h2 className="text-2xl font-bold text-text-primary">上传文档</h2>
        <p className="text-text-secondary mt-1">
          支持 PDF、PNG、JPG、TIFF、BMP 格式，最大 20MB
        </p>
      </div>

      {/* 未知模式：仅在确认无部门时提示，避免模板加载中时误显示 */}
      {uploadMode === 'unknown' && !profileLoading && !tenantCode && (
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

      {/* merge 模式：显示合并上传说明 */}
      {uploadMode === 'merge' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Layers className="h-5 w-5 text-accent-400" />
              综合报告
            </CardTitle>
            <CardDescription>
              {tenantName && `${tenantName} - `}可上传 {mergeDocTypes.join(' 或 ')}（或两者）
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Badge variant="outline" className="text-accent-400 border-accent-400">
              合并模式 - 可上传 1-2 份文档
            </Badge>
          </CardContent>
        </Card>
      )}

      {/* single 模式：多模板时显示模板选择器 */}
      {uploadMode === 'single' && singleTemplates.length > 1 && (
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
                    selectedTemplateId === template.id
                      ? 'border-primary-500 bg-primary-500/10 text-primary-400'
                      : 'border-border-default hover:border-primary-500/50 text-text-secondary'
                  )}
                >
                  {template.name}
                </button>
              ))}
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

      {/* Upload Area - single 模式：需先选模板（多模板时）才显示上传区域 */}
      {!isCameraOpen && !selectedFile && uploadMode === 'single' && selectedTemplateId && (
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

      {/* Upload Area - merge 模式：多文件合并上传 */}
      {!isCameraOpen && uploadMode === 'merge' && mergeFiles.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Layers className="h-5 w-5 text-accent-400" />
              上传文档
            </CardTitle>
            <CardDescription>
              请分别上传 {mergeDocTypes.join(' 和 ')}
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
                disabled={isUploading || !canSubmitMerge || mergePhase !== 'idle'}
              >
                {mergePhase !== 'idle' ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    {mergePhase === 'uploading' ? '上传中...' : '识别处理中...'}
                  </>
                ) : (
                  <>
                    <UploadIcon className="h-4 w-4 mr-2" />
                    上传并合并处理
                  </>
                )}
              </Button>
              {mergePhase === 'idle' && !isUploading && (
                <Button variant="outline" onClick={clearSelection}>
                  重新选择
                </Button>
              )}
            </div>

            {/* 合并进度条 */}
            {mergePhase !== 'idle' && (
              <div className="pt-3 space-y-2">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-text-secondary">
                    {mergePhase === 'uploading'
                      ? '正在上传文件...'
                      : '正在识别提取，预计 1–2 分钟，请勿关闭页面...'}
                  </span>
                  <span className="text-text-muted tabular-nums">{mergeProgress}%</span>
                </div>
                <div className="w-full h-2 bg-bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary-500 rounded-full transition-all duration-300 ease-out"
                    style={{ width: `${mergeProgress}%` }}
                  />
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Selected File Preview - single 模式 */}
      {selectedFile && !isCameraOpen && uploadMode === 'single' && (
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
              {uploadMode === 'single' ? (
                <span>选择文档类型后上传，系统将自动提取关键信息</span>
              ) : uploadMode === 'merge' ? (
                <span>请上传 {mergeDocTypes.join(' 和 ')}，系统将分别提取后合并结果</span>
              ) : (
                <span>请先选择所属部门</span>
              )}
            </li>
            {uploadMode === 'merge' && (
              <li className="flex items-start gap-2">
                <Layers className="h-4 w-4 mt-0.5 text-accent-400" />
                <span>合并模式：分别上传 {mergeDocTypes.join(' 和 ')}，系统将提取关键参数并生成综合报告</span>
              </li>
            )}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

