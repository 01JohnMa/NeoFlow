import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import documentsService from '@/services/documents'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { CompositeGroupEditor } from '@/features/composite-upload/components/CompositeGroupEditor'
import {
  buildCompositeBatchPayload,
  createEmptyCompositeGroup,
  getDefaultCompositeGroupPushName,
  getSubmittableCompositeGroups,
  getSubmittableCompositeUploadFiles,
  isCompositeFileUsedInOtherGroups,
  validateCompositeGroups,
  summarizeCompositeGroups,
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

  const handleGroupFileChange = useCallback(async (groupId: string, slotKey: CompositeSlotKey, file: File | null) => {
    if (!file) {
      setGroups(prev => prev.map(group => (
        group.id === groupId
          ? { ...group, documents: { ...group.documents, [slotKey]: null } }
          : group
      )))
      return
    }

    const error = validateFile(file)
    if (error) {
      setUploadError(error)
      return
    }

    if (isCompositeFileUsedInOtherGroups(groups, groupId, file)) {
      setUploadError('该文件已在其他分组中使用，请勿重复上传同一文件')
      return
    }

    const uploadedFile = await createCompositeUploadedFile(file)
    setUploadError(null)
    setGroups(prev => prev.map(group => (
      group.id === groupId
        ? { ...group, documents: { ...group.documents, [slotKey]: uploadedFile } }
        : group
    )))
  }, [createCompositeUploadedFile, groups])

  const batchSummary = useMemo(
    () => summarizeCompositeGroups(groups, scenario),
    [groups, scenario],
  )
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
  const groupEffectivePushNames = useMemo(
    () => Object.fromEntries(
      groups.map(group => [
        group.id,
        (groupCustomPushNames[group.id] || '').trim() || getDefaultCompositeGroupPushName(group, scenario),
      ]),
    ),
    [groupCustomPushNames, groups, scenario],
  )

  const handleBatchSubmit = async () => {
    if (!batchValidation.canSubmit) {
      setUploadError(batchValidation.globalErrors[0] || '当前仍有未满足提交条件的分组')
      return
    }

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
            Object.entries(group.documents).map(([currentSlotKey, currentUploadedFile]) => {
              if (currentUploadedFile?.id === currentFile.id) {
                return [
                  currentSlotKey,
                  { ...currentUploadedFile, documentId: result.document_id, filePath: result.file_path },
                ]
              }
              return [currentSlotKey, currentUploadedFile]
            }),
          ),
        })))
      }

      setBatchPhase('processing')
      setBatchProgress(20)

      const latestGroups = submittableGroups.map(group => ({
        ...group,
        documents: Object.fromEntries(
          Object.entries(group.documents).map(([slotKey, file]) => {
            if (!file) return [slotKey, null]
            return [
              slotKey,
              {
                ...file,
                documentId: uploadResults[file.id]?.document_id || file.documentId,
                filePath: uploadResults[file.id]?.file_path || file.filePath,
              },
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
        throw new Error('没有可提交的有效任务，请检查分组和模板配置')
      }

      const { job_id } = await documentsService.submitBatchProcess(items)

      await new Promise<void>((resolve, reject) => {
        batchTimerRef.current = setInterval(async () => {
          try {
            const jobStatus = await documentsService.getBatchJobStatus(job_id)
            setBatchProgress(Math.max(20, jobStatus.progress))

            if (jobStatus.status === 'completed') {
              stopBatchTimer()
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
        <CardDescription>
          {scenario.description}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <CompositeGroupEditor
          scenario={scenario}
          groups={groups}
          groupErrors={batchValidation.groupErrors}
          groupCustomPushNames={groupCustomPushNames}
          groupEffectivePushNames={groupEffectivePushNames}
          disabled={batchPhase !== 'idle'}
          onAddGroup={() => setGroups(prev => [...prev, createEmptyCompositeGroup(scenario)])}
          onUpdateGroupFile={handleGroupFileChange}
          onUpdateGroupCustomPushName={(groupId, value) => {
            setGroupCustomPushNames(prev => ({
              ...prev,
              [groupId]: value,
            }))
          }}
          onApplyGroupRecommendedName={(groupId) => {
            const targetGroup = groups.find(group => group.id === groupId)
            const defaultName = targetGroup ? getDefaultCompositeGroupPushName(targetGroup, scenario) : ''
            setGroupCustomPushNames(prev => ({
              ...prev,
              [groupId]: defaultName,
            }))
          }}
          onRemoveGroup={(groupId) => {
            setGroups(prev => {
              const next = prev.filter(group => group.id !== groupId)
              return next.length > 0 ? next : [createEmptyCompositeGroup(scenario)]
            })
            setGroupCustomPushNames(prev => {
              const next = { ...prev }
              delete next[groupId]
              return next
            })
          }}
        />

        <div className="rounded-lg border border-border-default bg-bg-secondary/50 p-3 text-sm text-text-secondary">
          <div>任务摘要</div>
          <div className="mt-1 text-text-muted">
            完整组 {batchSummary.complete} / 部分组 {batchSummary.partial} / 空组 {batchSummary.empty} / 共 {batchSummary.totalTasks} 项任务
          </div>
          <div className="mt-1 text-text-muted">
            当前可提交 {batchValidation.validTaskCount} 项，实际将上传 {submittableFiles.length} 个组内文件。
          </div>
          {batchSummary.totalTasks > scenario.maxGroups && (
            <div className="mt-1 text-error-500">当前任务数已超过上限。</div>
          )}
        </div>

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
