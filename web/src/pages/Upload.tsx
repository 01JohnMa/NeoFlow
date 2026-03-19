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
  Plus,
  AlertTriangle,
  FolderUp,
} from 'lucide-react'
import { BatchMergePairing } from '@/components/BatchMergePairing'
import type { UploadedFile, MergePair } from '@/components/BatchMergePairing'
import type { BatchProcessItem } from '@/types'

// ============ 上传模式配置（数据驱动：根据模板数据自动判断）============

// 上传模式类型：single=单文件手动选模板模式，batch=批量模式
type UploadMode = 'single' | 'batch' | 'unknown'

// 当前激活的 Tab（用户可手动切换到 batch）
type ActiveTab = 'default' | 'batch'

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
  const uploadMultipleMutation = useUploadMultiple()
  const { tenantName, tenantCode, templates, isLoading: profileLoading } = useProfile()

  // ============ 数据驱动：根据模板数据自动判断上传模式 ============
  // 有模板 → single 模式；无部门 → unknown
  const uploadMode: UploadMode = useMemo(() => {
    if (!tenantCode) return 'unknown'
    if (templates.some(t => t.is_active !== false)) return 'single'
    return 'unknown'
  }, [tenantCode, templates])

  // single 模式可用的模板列表（所有 is_active 模板）
  const singleTemplates = useMemo(
    () => templates.filter(t => t.is_active !== false),
    [templates]
  )
  const isMobile = useMemo(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(pointer: coarse)').matches
  }, [])
  const fileAccept = isMobile ? 'image/*,application/pdf' : '.pdf,.png,.jpg,.jpeg,.tiff,.bmp'

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null)
  // single 模式：用户选中的模板 ID（单模板时自动选中）
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null)

  // ============ 批量模式状态 ============
  const [activeTab, setActiveTab] = useState<ActiveTab>('default')
  const [batchFiles, setBatchFiles] = useState<UploadedFile[]>([])
  const [batchSingleAssignments, setBatchSingleAssignments] = useState<Record<string, string>>({})
  const [batchMergePairs, setBatchMergePairs] = useState<MergePair[]>([])
  const [batchPhase, setBatchPhase] = useState<'idle' | 'uploading' | 'processing'>('idle')
  const [batchProgress, setBatchProgress] = useState(0)
  const batchFileInputRef = useRef<HTMLInputElement>(null)
  const batchTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopBatchTimer = useCallback(() => {
    if (batchTimerRef.current) {
      clearInterval(batchTimerRef.current)
      batchTimerRef.current = null
    }
  }, [])

  // single 模式：只有一个模板时自动选中
  useEffect(() => {
    if (uploadMode === 'single' && singleTemplates.length === 1) {
      setSelectedTemplateId(singleTemplates[0].id)
    }
  }, [uploadMode, singleTemplates])

  // 组件卸载时清理定时器
  useEffect(() => {
    return () => { stopBatchTimer() }
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

  // ============ 批量模式处理函数 ============

  const handleBatchFileAdd = useCallback((fileList: FileList) => {
    const newFiles: UploadedFile[] = []
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i]
      const error = validateFile(file)
      if (error) {
        setUploadError(error)
        return
      }
      const id = `batch-${Date.now()}-${i}`
      let preview: string | null = null
      if (file.type.startsWith('image/')) {
        const reader = new FileReader()
        reader.onload = (e) => {
          setBatchFiles(prev =>
            prev.map(f => f.id === id ? { ...f, preview: e.target?.result as string } : f)
          )
        }
        reader.readAsDataURL(file)
      }
      newFiles.push({ id, file, preview })
    }
    setUploadError(null)
    setBatchFiles(prev => {
      const total = prev.length + newFiles.length
      if (total > 10) {
        setUploadError('最多选择 10 个文件')
        return prev
      }
      return [...prev, ...newFiles]
    })
  }, [])

  const removeBatchFile = useCallback((fileId: string) => {
    setBatchFiles(prev => prev.filter(f => f.id !== fileId))
    setBatchSingleAssignments(prev => {
      const next = { ...prev }
      delete next[fileId]
      return next
    })
    // 移除包含该文件的配对
    setBatchMergePairs(prev =>
      prev.filter(p => p.fileA?.id !== fileId && p.fileB?.id !== fileId)
    )
  }, [])

  // 计算未配对的文件（排除已分配为 merge 的文件）
  const pairedFileIds = useMemo(() => {
    const ids = new Set<string>()
    batchMergePairs.forEach(p => {
      if (p.fileA) ids.add(p.fileA.id)
      if (p.fileB) ids.add(p.fileB.id)
    })
    return ids
  }, [batchMergePairs])

  const unpairedBatchFiles = useMemo(
    () => batchFiles.filter(f => !pairedFileIds.has(f.id)),
    [batchFiles, pairedFileIds]
  )

  // 计算任务项数量
  const batchTaskCount = useMemo(() => {
    const singleCount = Object.keys(batchSingleAssignments).filter(
      fid => !pairedFileIds.has(fid)
    ).length
    return singleCount + batchMergePairs.length
  }, [batchSingleAssignments, pairedFileIds, batchMergePairs])

  const handleBatchSubmit = async () => {
    if (batchTaskCount === 0) {
      setUploadError('请至少分配一个任务')
      return
    }
    if (batchTaskCount > 5) {
      setUploadError(`任务项不能超过 5 个（当前 ${batchTaskCount} 个）`)
      return
    }

    setUploadError(null)
    setBatchPhase('uploading')
    setBatchProgress(0)

    try {
      // 1. 上传所有文件
      const allFiles = batchFiles.filter(f => !f.documentId)
      const uploadResults: Record<string, { document_id: string; file_path: string }> = {}

      for (let i = 0; i < allFiles.length; i++) {
        const f = allFiles[i]
        const result = await documentsService.upload(f.file, {
          onProgress: (p) => {
            const totalProgress = Math.round(((i + p / 100) / allFiles.length) * 20)
            setBatchProgress(totalProgress)
          },
        })
        uploadResults[f.id] = { document_id: result.document_id, file_path: result.file_path }
        setBatchFiles(prev =>
          prev.map(bf => bf.id === f.id
            ? { ...bf, documentId: result.document_id, filePath: result.file_path }
            : bf
          )
        )
      }

      // 2. 构建 batch items
      setBatchPhase('processing')
      setBatchProgress(20)

      const items: BatchProcessItem[] = []

      // single 任务
      for (const [fileId, templateId] of Object.entries(batchSingleAssignments)) {
        if (pairedFileIds.has(fileId)) continue
        const docId = uploadResults[fileId]?.document_id
          || batchFiles.find(f => f.id === fileId)?.documentId
        if (docId) {
          items.push({ document_id: docId, template_id: templateId })
        }
      }

      // merge 任务：只提交一条，后端 _process_merge_item 负责同时处理 A 和 B
      for (const pair of batchMergePairs) {
        const docIdA = pair.fileA ? (uploadResults[pair.fileA.id]?.document_id || pair.fileA.documentId) : undefined
        const docIdB = pair.fileB ? (uploadResults[pair.fileB.id]?.document_id || pair.fileB.documentId) : undefined
        if (docIdA && docIdB) {
          items.push({
            document_id: docIdA,
            template_id: pair.templateIdA,
            paired_document_id: docIdB,
            paired_template_id: pair.templateIdB,
          })
        }
      }

      // 3. 提交批量处理
      const { job_id } = await documentsService.submitBatchProcess(items)

      // 4. 轮询状态
      await new Promise<void>((resolve, reject) => {
        batchTimerRef.current = setInterval(async () => {
          try {
            const jobStatus = await documentsService.getBatchJobStatus(job_id)
            setBatchProgress(Math.max(20, jobStatus.progress))

            if (jobStatus.status === 'completed') {
              stopBatchTimer()
              setBatchProgress(100)
              await new Promise(r => setTimeout(r, 600))
              const firstDocId = jobStatus.document_ids?.[0]
              navigate(firstDocId ? `/documents/${firstDocId}` : '/documents')
              resolve()
            } else if (jobStatus.status === 'failed') {
              stopBatchTimer()
              reject(new Error(jobStatus.error || '批量处理失败'))
            }
          } catch {
            // 单次轮询失败不中断
          }
        }, 3000)
      })
    } catch (err) {
      stopBatchTimer()
      setBatchPhase('idle')
      setBatchProgress(0)
      const message = err instanceof Error ? err.message : '批量处理失败'
      setUploadError(message)
    }
  }

  const clearBatch = () => {
    setBatchFiles([])
    setBatchSingleAssignments({})
    setBatchMergePairs([])
    setBatchPhase('idle')
    setBatchProgress(0)
    setUploadError(null)
    stopBatchTimer()
  }

  const isUploading = uploadMutation.isPending || processMutation.isPending ||
                      uploadMultipleMutation.isPending || batchPhase !== 'idle'

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fadeIn">
      <div>
        <h2 className="text-2xl font-bold text-text-primary">上传文档</h2>
        <p className="text-text-secondary mt-1">
          支持 PDF、PNG、JPG、TIFF、BMP 格式，最大 20MB
        </p>
      </div>

      {/* Tab 切换：默认模式 / 批量模式 */}
      {tenantCode && templates.length > 0 && (
        <div className="flex gap-2 border-b border-border-default pb-2">
          <button
            onClick={() => { setActiveTab('default'); clearBatch() }}
            className={cn(
              'px-4 py-2 text-sm rounded-t-lg transition-colors',
              activeTab === 'default'
                ? 'bg-primary-500/10 text-primary-400 border-b-2 border-primary-500'
                : 'text-text-secondary hover:text-text-primary'
            )}
          >
            单文件上传
          </button>
          <button
            onClick={() => { setActiveTab('batch'); clearSelection() }}
            className={cn(
              'px-4 py-2 text-sm rounded-t-lg transition-colors flex items-center gap-1',
              activeTab === 'batch'
                ? 'bg-primary-500/10 text-primary-400 border-b-2 border-primary-500'
                : 'text-text-secondary hover:text-text-primary'
            )}
          >
            <FolderUp className="h-4 w-4" />
            批量上传
          </button>
        </div>
      )}

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

      {/* single 模式：多模板时显示模板选择器 */}
      {activeTab === 'default' && uploadMode === 'single' && singleTemplates.length > 1 && (
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
      {!isCameraOpen && !selectedFile && activeTab === 'default' && uploadMode === 'single' && selectedTemplateId && (
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

      {/* Selected File Preview - single 模式 */}
      {selectedFile && !isCameraOpen && activeTab === 'default' && uploadMode === 'single' && (
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

      {/* ============ 批量模式 UI ============ */}
      {activeTab === 'batch' && tenantCode && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <FolderUp className="h-5 w-5 text-primary-400" />
                批量上传
              </CardTitle>
              <CardDescription>
                选择 1～10 个文件，为每个文件指定模板或配对合并。最多 5 个任务项。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* 文件选择区域 */}
              <div
                className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all hover:border-primary-500/50 hover:bg-bg-hover"
                onClick={() => batchFileInputRef.current?.click()}
              >
                <input
                  ref={batchFileInputRef}
                  type="file"
                  accept={fileAccept}
                  multiple
                  onChange={(e) => {
                    if (e.target.files) handleBatchFileAdd(e.target.files)
                    e.target.value = ''
                  }}
                  className="hidden"
                />
                <Plus className="h-8 w-8 text-text-muted mx-auto mb-2" />
                <p className="text-sm text-text-muted">点击选择文件（可多选）</p>
              </div>

              {/* 已选文件列表 + 模板分配 */}
              {batchFiles.length > 0 && (
                <div className="space-y-3">
                  <Label className="text-sm font-medium text-text-secondary">
                    已选文件（{batchFiles.length} 个）
                  </Label>
                  {batchFiles.map(f => (
                    <div
                      key={f.id}
                      className={cn(
                        'flex items-center gap-3 p-3 rounded-lg border',
                        pairedFileIds.has(f.id)
                          ? 'bg-accent-400/5 border-accent-400/30'
                          : 'bg-bg-secondary border-border-default'
                      )}
                    >
                      <div className="w-10 h-10 rounded bg-bg-hover flex items-center justify-center flex-shrink-0">
                        {f.preview ? (
                          <img src={f.preview} alt="" className="w-full h-full object-cover rounded" />
                        ) : (
                          <FileText className="h-5 w-5 text-text-muted" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-text-primary truncate">{f.file.name}</p>
                        <p className="text-xs text-text-muted">{formatFileSize(f.file.size)}</p>
                      </div>
                      {pairedFileIds.has(f.id) ? (
                        <Badge variant="outline" className="text-accent-400 border-accent-400 text-xs flex-shrink-0">
                          已配对
                        </Badge>
                      ) : (
                        <select
                          value={batchSingleAssignments[f.id] || ''}
                          onChange={e => {
                            const val = e.target.value
                            setBatchSingleAssignments(prev => {
                              if (!val) {
                                const next = { ...prev }
                                delete next[f.id]
                                return next
                              }
                              return { ...prev, [f.id]: val }
                            })
                          }}
                          className="w-36 rounded-md border border-border-default bg-bg-primary px-2 py-1 text-xs flex-shrink-0"
                        >
                          <option value="">选择模板...</option>
                          {singleTemplates.map(t => (
                            <option key={t.id} value={t.id}>{t.name}</option>
                          ))}
                        </select>
                      )}
                      {batchPhase === 'idle' && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-text-muted hover:text-error-500 flex-shrink-0"
                          onClick={() => removeBatchFile(f.id)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Merge 配对区域 */}
              {batchFiles.length >= 2 && (
                <BatchMergePairing
                  allTemplates={templates}
                  unpairedFiles={unpairedBatchFiles.filter(f => !batchSingleAssignments[f.id])}
                  pairs={batchMergePairs}
                  onCreatePair={(pair) => setBatchMergePairs(prev => [...prev, pair])}
                  onRemovePair={(pairId) => setBatchMergePairs(prev => prev.filter(p => p.id !== pairId))}
                />
              )}

              {/* 任务统计 */}
              {batchFiles.length > 0 && (
                <div className="flex items-center justify-between text-sm text-text-secondary pt-2 border-t border-border-default">
                  <span>
                    任务项: {batchTaskCount} / 5
                    {batchTaskCount > 5 && (
                      <span className="text-error-500 ml-2">（超出上限）</span>
                    )}
                  </span>
                  <span className="text-text-muted">
                    single: {Object.keys(batchSingleAssignments).filter(fid => !pairedFileIds.has(fid)).length}
                    {batchMergePairs.length > 0 && ` / merge: ${batchMergePairs.length}`}
                  </span>
                </div>
              )}

              {/* Error */}
              {uploadError && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-error-500/10 border border-error-500/20 text-error-500 text-sm">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}

              {/* 提交按钮 */}
              {batchFiles.length > 0 && (
                <div className="pt-2 flex gap-3">
                  <Button
                    className="flex-1"
                    onClick={handleBatchSubmit}
                    disabled={batchPhase !== 'idle' || batchTaskCount === 0 || batchTaskCount > 5}
                  >
                    {batchPhase !== 'idle' ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        {batchPhase === 'uploading' ? '上传中...' : '批量处理中...'}
                      </>
                    ) : (
                      <>
                        <UploadIcon className="h-4 w-4 mr-2" />
                        提交批量处理（{batchTaskCount} 项）
                      </>
                    )}
                  </Button>
                  {batchPhase === 'idle' && (
                    <Button variant="outline" onClick={clearBatch}>
                      清空
                    </Button>
                  )}
                </div>
              )}

              {/* 批量进度条 */}
              {batchPhase !== 'idle' && (
                <div className="pt-3 space-y-2">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-text-secondary">
                      {batchPhase === 'uploading'
                        ? '正在上传文件...'
                        : '正在批量处理，请勿关闭页面...'}
                    </span>
                    <span className="text-text-muted tabular-nums">{batchProgress}%</span>
                  </div>
                  <div className="w-full h-2 bg-bg-secondary rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary-500 rounded-full transition-all duration-300 ease-out"
                      style={{ width: `${batchProgress}%` }}
                    />
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </>
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
              ) : (
                <span>请先选择所属部门</span>
              )}
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

