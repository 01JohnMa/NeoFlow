import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import documentsService from '@/services/documents'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { CompositeGroupEditor } from '@/features/composite-upload/components/CompositeGroupEditor'
import {
  buildCompositeBatchPayload,
  createEmptyCompositeGroup,
  createEmptyCompositeGroupSeededFromFirst,
  getDefaultCompositeGroupPushName,
  getSubmittableCompositeGroups,
  getSubmittableCompositeUploadFiles,
  isCompositeFileUsedInOtherGroups,
  validateCompositeGroups,
} from '@/features/composite-upload/core/compositeUpload'
import type { CompositeGroup, CompositeScenarioConfig, CompositeSlotKey, CompositeUploadedFile } from '@/features/composite-upload/core/types'
import {
  AlertCircle,
  FolderUp,
  Loader2,
  Upload as UploadIcon,
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

interface CompositeUploadPanelProps {
  scenario: CompositeScenarioConfig
}

export function CompositeUploadPanel({ scenario }: CompositeUploadPanelProps) {
  const navigate = useNavigate()
  const [groups, setGroups] = useState<CompositeGroup[]>(() => [createEmptyCompositeGroup(scenario)])
  const [groupCustomPushNames, setGroupCustomPushNames] = useState<Record<string, string>>({})
  const [batchPhase, setBatchPhase] = useState<'idle' | 'uploading' | 'processing'>('idle')
  const [batchProgress, setBatchProgress] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const batchTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const isSubmittingRef = useRef(false)

  const stopBatchTimer = useCallback(() => {
    if (batchTimerRef.current) {
      clearInterval(batchTimerRef.current)
      batchTimerRef.current = null
    }
  }, [])

  useEffect(() => {
    setGroups([createEmptyCompositeGroup(scenario)])
    setGroupCustomPushNames({})
    setBatchPhase('idle')
    setBatchProgress(0)
    setUploadError(null)
  }, [scenario])

  useEffect(() => {
    return () => { stopBatchTimer() }
  }, [stopBatchTimer])

  // 当分组有文件后自动填入默认推送名（仅首次，用户清空后不再回填）
  useEffect(() => {
    setGroupCustomPushNames(prev => {
      const next = { ...prev }
      let changed = false
      groups.forEach(group => {
        if (!(group.id in next)) {
          const defaultName = getDefaultCompositeGroupPushName(group, scenario)
          if (defaultName) {
            next[group.id] = defaultName
            changed = true
          }
        }
      })
      return changed ? next : prev
    })
  }, [groups, scenario])

  const validateFile = (file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return '不支持的文件格式，请上传 PDF、PNG、JPG、TIFF 或 BMP 文件'
    }
    if (file.size > MAX_FILE_SIZE) {
      return `文件大小超过限制（最大 ${Math.round(MAX_FILE_SIZE / 1024 / 1024)} MB）`
    }
    return null
  }

  const createCompositeUploadedFile = useCallback((file: File): Promise<CompositeUploadedFile> => {
    const id = `composite-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

    return new Promise((resolve) => {
      if (!file.type.startsWith('image/')) {
        resolve({ id, file, preview: null })
        return
      }

      const reader = new FileReader()
      reader.onload = (event) => {
        resolve({ id, file, preview: event.target?.result as string })
      }
      reader.onerror = () => {
        resolve({ id, file, preview: null })
      }
      reader.readAsDataURL(file)
    })
  }, [])

  const handleGroupFileChange = useCallback(async (groupId: string, slotKey: CompositeSlotKey, files: File[]) => {
    if (files.length === 0) {
      setGroups(prev => prev.map(group => (
        group.id === groupId
          ? { ...group, documents: { ...group.documents, [slotKey]: [] } }
          : group
      )))
      return
    }

    const currentGroup = groups.find(group => group.id === groupId)
    const existingSlotFiles = currentGroup?.documents[slotKey] || []
    const existingIdentities = new Set(existingSlotFiles.map(file => `${file.file.name}::${file.file.size}::${file.file.lastModified}::${file.file.type}`))
    const pendingUploads: File[] = []

    for (const file of files) {
      const error = validateFile(file)
      if (error) {
        setUploadError(error)
        return
      }

      if (isCompositeFileUsedInOtherGroups(groups, groupId, file)) {
        setUploadError('该文件已在其他分组中使用，请勿重复上传同一文件')
        return
      }

      const identity = `${file.name}::${file.size}::${file.lastModified}::${file.type}`
      if (existingIdentities.has(identity)) {
        continue
      }
      existingIdentities.add(identity)
      pendingUploads.push(file)
    }

    if (pendingUploads.length === 0) {
      setUploadError(null)
      return
    }

    const uploadedFiles = await Promise.all(pendingUploads.map(file => createCompositeUploadedFile(file)))
    setUploadError(null)
    setGroups(prev => prev.map(group => (
      group.id === groupId
        ? {
            ...group,
            documents: {
              ...group.documents,
              [slotKey]: [...group.documents[slotKey], ...uploadedFiles],
            },
          }
        : group
    )))
  }, [createCompositeUploadedFile, groups])

  const batchValidation = useMemo(
    () => validateCompositeGroups(groups, scenario),
    [groups, scenario],
  )
  const submittableGroups = useMemo(
    () => getSubmittableCompositeGroups(groups, scenario),
    [groups, scenario],
  )
  const submittableFiles = useMemo(
    () => getSubmittableCompositeUploadFiles(groups, scenario),
    [groups, scenario],
  )
  const handleBatchSubmit = async () => {
    if (isSubmittingRef.current) return
    if (!batchValidation.canSubmit) {
      setUploadError(batchValidation.globalErrors[0] || '当前仍有未满足提交条件的分组')
      return
    }

    isSubmittingRef.current = true
    setUploadError(null)
    setBatchPhase('uploading')
    setBatchProgress(0)

    try {
      const uploadResults: Record<string, { document_id: string; file_path: string }> = {}
      const { fileCustomPushNameMap } = buildCompositeBatchPayload({
        groups: submittableGroups,
        scenario,
        uploadResults: {},
        groupCustomPushNames,
      })

      const filesToUpload = submittableFiles.filter(file => !file.documentId)

      for (let i = 0; i < filesToUpload.length; i += 1) {
        const currentFile = filesToUpload[i]
        const result = await documentsService.upload(currentFile.file, {
          customPushName: fileCustomPushNameMap[currentFile.id] || undefined,
          onProgress: (progress) => {
            const totalProgress = Math.round(((i + progress / 100) / Math.max(filesToUpload.length, 1)) * 20)
            setBatchProgress(totalProgress)
          },
        })

        uploadResults[currentFile.id] = {
          document_id: result.document_id,
          file_path: result.file_path,
        }

        setGroups(prev => prev.map(group => ({
          ...group,
          documents: Object.fromEntries(
            Object.entries(group.documents).map(([currentSlotKey, currentUploadedFiles]) => {
              const hasCurrentFile = currentUploadedFiles.some(file => file.id === currentFile.id)
              if (hasCurrentFile) {
                return [
                  currentSlotKey,
                  currentUploadedFiles.map((file) => (
                    file.id === currentFile.id
                      ? { ...file, documentId: result.document_id, filePath: result.file_path }
                      : file
                  )),
                ]
              }
              return [currentSlotKey, currentUploadedFiles]
            }),
          ),
        })))
      }

      setBatchPhase('processing')
      setBatchProgress(20)

      const latestGroups = submittableGroups.map(group => ({
        ...group,
        documents: Object.fromEntries(
          Object.entries(group.documents).map(([slotKey, files]) => {
            return [
              slotKey,
              files.map((file) => ({
                ...file,
                documentId: uploadResults[file.id]?.document_id || file.documentId,
                filePath: uploadResults[file.id]?.file_path || file.filePath,
              })),
            ]
          }),
        ),
      }))

      const { items } = buildCompositeBatchPayload({
        groups: latestGroups,
        scenario,
        uploadResults,
        groupCustomPushNames,
      })

      if (items.length === 0) {
        throw new Error('没有可提交的有效任务，请检查分组和文档类型选择')
      }

      const { job_id } = await documentsService.submitBatchProcess(items)

      await new Promise<void>((resolve, reject) => {
        batchTimerRef.current = setInterval(async () => {
          try {
            const jobStatus = await documentsService.getBatchJobStatus(job_id)
            setBatchProgress(Math.max(20, jobStatus.progress))

            if (jobStatus.status === 'completed') {
              stopBatchTimer()
              isSubmittingRef.current = false
              setBatchProgress(100)
              await new Promise(innerResolve => setTimeout(innerResolve, 600))
              const firstDocId = jobStatus.document_ids?.[0]
              navigate(firstDocId ? `/documents/${firstDocId}` : '/documents')
              resolve()
            } else if (jobStatus.status === 'failed') {
              stopBatchTimer()
              reject(new Error(jobStatus.error || '批量处理失败'))
            }
          } catch {
            // 单次轮询失败不中断流程
          }
        }, 3000)
      })
    } catch (error) {
      stopBatchTimer()
      isSubmittingRef.current = false
      setBatchPhase('idle')
      setBatchProgress(0)
      const message = error instanceof Error ? error.message : '批量处理失败'
      setUploadError(message)
    }
  }

  const clearBatch = () => {
    setGroups([createEmptyCompositeGroup(scenario)])
    setGroupCustomPushNames({})
    setBatchPhase('idle')
    setBatchProgress(0)
    setUploadError(null)
    stopBatchTimer()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <FolderUp className="h-5 w-5 text-primary-400" />
          {scenario.displayName}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
          <CompositeGroupEditor
            scenario={scenario}
            groups={groups}
            groupErrors={batchValidation.groupErrors}
            disabled={batchPhase !== 'idle'}
            renderGroupAside={(group) => {
              const effectiveValue = groupCustomPushNames[group.id] ?? ''

              return (
                <div className="rounded-lg border border-border-default bg-bg-secondary/40 px-2.5 py-2" aria-label="推送文件名">
                  <div className="flex items-center gap-2">
                    <div className="shrink-0 text-[11px] font-medium text-text-secondary">推送名</div>
                    <Input
                      value={effectiveValue}
                      onChange={(e) => {
                        const nextValue = e.target.value
                        setGroupCustomPushNames(prev => ({ ...prev, [group.id]: nextValue }))
                      }}
                      aria-label="推送文件名"
                      maxLength={100}
                      disabled={batchPhase !== 'idle'}
                      className="h-8 min-w-0 flex-1 text-xs"
                    />
                  </div>
                </div>
              )
            }}
            onAddGroup={() => setGroups(prev => [
              ...prev,
              createEmptyCompositeGroupSeededFromFirst(scenario, prev[0]),
            ])}
            onUpdateGroupTemplateSelection={(groupId, slotKey, templateId) => {
              setGroups(prev => prev.map(group => (
                group.id === groupId
                  ? {
                      ...group,
                      templateSelections: {
                        ...group.templateSelections,
                        [slotKey]: templateId,
                      },
                    }
                  : group
              )))
            }}
            onUpdateGroupFile={handleGroupFileChange}
            onRemoveGroupFile={(groupId, slotKey, fileId) => {
              setGroups(prev => prev.map(group => (
                group.id === groupId
                  ? {
                      ...group,
                      documents: {
                        ...group.documents,
                        [slotKey]: group.documents[slotKey].filter(file => file.id !== fileId),
                      },
                    }
                  : group
              )))
            }}
            onRemoveGroup={(groupId) => {
              setGroups(prev => {
                const next = prev.filter(g => g.id !== groupId)
                return next.length > 0 ? next : [createEmptyCompositeGroup(scenario)]
              })
              setGroupCustomPushNames(prev => {
                const next = { ...prev }
                delete next[groupId]
                return next
              })
            }}
          />

        {batchValidation.globalErrors.length > 0 && (
          <div className="space-y-2 rounded-lg border border-error-500/20 bg-error-500/10 p-3 text-sm text-error-500">
            {batchValidation.globalErrors.map(error => (
              <div key={error} className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            ))}
          </div>
        )}

        {uploadError && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-error-500/10 border border-error-500/20 text-error-500 text-sm">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{uploadError}</span>
          </div>
        )}

        {groups.length > 0 && (
          <div className="pt-2 flex gap-3">
            <Button
              className="flex-1"
              onClick={handleBatchSubmit}
              disabled={batchPhase !== 'idle' || !batchValidation.canSubmit}
            >
              {batchPhase !== 'idle' ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  {batchPhase === 'uploading' ? '上传中...' : '批量处理中...'}
                </>
              ) : (
                <>
                  <UploadIcon className="h-4 w-4 mr-2" />
                  提交批量处理（{batchValidation.validTaskCount} 项）
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
  )
}
