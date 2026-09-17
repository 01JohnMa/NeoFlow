import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { documentsService } from '@/services/documents'
import { parseService, type ParseMode } from '@/services/parse'
import { useProfile } from '@/hooks/useProfile'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { PageContent } from '@/components/parse-playground/PageContent'
import { pagePlainText, resultFullText } from '@/lib/parseContent'
import { cn, formatDate } from '@/lib/utils'
import type { ParsePage, ParseResult, ProcessingJob } from '@/types'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  History,
  Maximize2,
  Play,
  Upload,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'

type ChunkStatus = 'uploading' | 'upload-failed' | 'ready' | 'running' | 'done' | 'failed'

interface FileChunk {
  key: string
  name: string
  documentId?: string
  status: ChunkStatus
  jobId?: string
  error?: string
}

const MODE_STORAGE_KEY = 'nf.parse.mode'

function jobStatusToChunk(status: string): ChunkStatus {
  if (status === 'completed') return 'done'
  if (status === 'failed') return 'failed'
  if (status === 'queued' || status === 'processing') return 'running'
  return 'running'
}

function chunkStatusLabel(status: ChunkStatus): string {
  switch (status) {
    case 'uploading':
      return '上传中'
    case 'upload-failed':
      return '上传失败'
    case 'ready':
      return '待解析'
    case 'running':
      return '解析中'
    case 'done':
      return '已解析'
    case 'failed':
      return '解析失败'
  }
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  const err = error as { response?: { data?: { error?: string; detail?: string } } }
  const detail = err?.response?.data?.error || err?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function StatusDot({ status }: { status: ChunkStatus }) {
  const color = {
    uploading: 'bg-warning-500',
    'upload-failed': 'bg-error-500',
    ready: 'bg-text-muted',
    running: 'bg-primary-500 animate-pulse',
    done: 'bg-success-500',
    failed: 'bg-error-500',
  }[status]
  return <span className={cn('inline-block h-2 w-2 rounded-full', color)} aria-hidden="true" />
}

function DocumentPreview({
  documentId,
  fileName,
  page,
  pageCount,
  onPageChange,
}: {
  documentId: string
  fileName: string
  page: number
  pageCount: number | null
  onPageChange: (page: number) => void
}) {
  const [scale, setScale] = useState(1)
  const containerRef = useRef<HTMLDivElement>(null)

  const blobQuery = useQuery({
    queryKey: ['document-blob', documentId],
    queryFn: () => documentsService.fetchFileBlob(documentId),
    staleTime: Infinity,
    gcTime: Infinity,
  })

  const objectUrl = useMemo(() => {
    if (!blobQuery.data) return null
    return URL.createObjectURL(blobQuery.data)
  }, [blobQuery.data])

  useEffect(() => {
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [objectUrl])

  const kind = blobQuery.data?.type && blobQuery.data.type.startsWith('image/') ? 'image' : 'pdf'
  const canPrev = page > 1
  const canNext = pageCount ? page < pageCount : true

  return (
    <div ref={containerRef} className="flex h-full flex-col bg-bg-secondary">
      <div className="flex flex-wrap items-center gap-1 border-b border-border-default px-3 py-2 text-text-secondary">
        <Button variant="ghost" size="icon-sm" aria-label="上一页" disabled={!canPrev} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="min-w-[86px] text-center text-xs tabular-nums" aria-live="polite">
          {page}
          {pageCount ? ` / ${pageCount}` : ''}
        </span>
        <Button variant="ghost" size="icon-sm" aria-label="下一页" disabled={!canNext} onClick={() => onPageChange(page + 1)}>
          <ChevronRight className="h-4 w-4" />
        </Button>
        <div className="mx-2 h-4 w-px bg-border-default" />
        <Button variant="ghost" size="icon-sm" aria-label="缩小" onClick={() => setScale((s) => Math.max(0.5, s - 0.15))}>
          <ZoomOut className="h-4 w-4" />
        </Button>
        <span className="min-w-[44px] text-center text-xs tabular-nums">{Math.round(scale * 100)}%</span>
        <Button variant="ghost" size="icon-sm" aria-label="放大" onClick={() => setScale((s) => Math.min(2.5, s + 0.15))}>
          <ZoomIn className="h-4 w-4" />
        </Button>
        <div className="mx-2 h-4 w-px bg-border-default" />
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="下载原件"
          onClick={() => documentsService.download(documentId, fileName)}
        >
          <Download className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="全屏"
          onClick={() => containerRef.current?.requestFullscreen?.()}
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
        <span className="ml-auto max-w-[220px] truncate text-xs text-text-muted" title={fileName}>
          {fileName}
        </span>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {blobQuery.isLoading && (
          <div className="flex h-full items-center justify-center">
            <Spinner />
          </div>
        )}
        {blobQuery.isError && (
          <p className="py-12 text-center text-sm text-text-muted">原件预览加载失败，仍可查看解析结果</p>
        )}
        {objectUrl && (
          <div className="mx-auto origin-top transition-transform" style={{ transform: `scale(${scale})`, width: 'fit-content' }}>
            {kind === 'image' ? (
              <img src={objectUrl} alt={fileName} className="max-w-full" />
            ) : (
              <iframe
                src={`${objectUrl}#page=${page}&zoom=page-width&toolbar=0`}
                title={fileName}
                className="h-[70vh] w-[720px] max-w-full bg-white"
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function HistoryDrawer({
  open,
  currentUser,
  returnFocusTo,
  onClose,
  onOpenJob,
}: {
  open: boolean
  currentUser?: string
  returnFocusTo?: React.RefObject<HTMLButtonElement | null>
  onClose: () => void
  onOpenJob: (jobId: string) => void
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const historyQuery = useQuery({
    queryKey: ['parse-history', currentUser],
    queryFn: () => parseService.listJobs({ created_by: currentUser, limit: 50 }),
    enabled: open,
    staleTime: 15000,
  })

  useEffect(() => {
    if (!open) return
    const returnTarget = returnFocusTo?.current
    closeButtonRef.current?.focus()
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => {
      window.removeEventListener('keydown', handler)
      returnTarget?.focus()
    }
  }, [open, onClose, returnFocusTo])

  if (!open) return null

  const jobs = (historyQuery.data || []).filter(
    (job) => job.execution_spec?.capability === 'parse' || job.job_type === 'parse',
  )

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="解析历史">
      <button type="button" aria-label="关闭历史" className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-full max-w-md flex-col border-l border-border-default bg-bg-card">
        <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
          <h2 className="text-sm font-semibold text-text-primary">解析历史（我的）</h2>
          <Button ref={closeButtonRef} variant="ghost" size="icon-sm" aria-label="关闭" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-auto p-3">
          {historyQuery.isLoading ? (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          ) : jobs.length === 0 ? (
            <p className="py-10 text-center text-sm text-text-muted">暂无解析记录</p>
          ) : (
            <ul className="space-y-2">
              {jobs.map((job) => (
                <li key={job.job_id}>
                  <button
                    type="button"
                    onClick={() => onOpenJob(job.job_id)}
                    className="w-full rounded-lg border border-border-default p-3 text-left transition-colors hover:bg-bg-hover"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2 text-sm text-text-primary">
                        <StatusDot status={jobStatusToChunk(job.status)} />
                        {chunkStatusLabel(jobStatusToChunk(job.status))}
                      </span>
                      <span className="text-xs text-text-muted">{formatDate(job.created_at)}</span>
                    </div>
                    <p className="mt-1 truncate font-mono text-xs text-text-muted" title={job.job_id}>
                      {job.job_id}
                    </p>
                    {job.error && <p className="mt-1 truncate text-xs text-error-500">{job.error}</p>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

export function ParsePlayground() {
  const [chunks, setChunks] = useState<FileChunk[]>([])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [mode, setMode] = useState<ParseMode>(() => {
    const stored = window.localStorage.getItem(MODE_STORAGE_KEY)
    return stored === 'vlm' ? 'vlm' : 'pipeline'
  })
  const [targetPages, setTargetPages] = useState('')
  const [activeTab, setActiveTab] = useState<'build' | 'results'>('build')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')
  const [page, setPage] = useState(1)
  const [copied, setCopied] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const historyButtonRef = useRef<HTMLButtonElement>(null)
  const restoreAttempted = useRef(false)
  const docRestoreAttempted = useRef(false)
  const queryClient = useQueryClient()
  const { profile } = useProfile()

  useEffect(() => {
    window.localStorage.setItem(MODE_STORAGE_KEY, mode)
  }, [mode])

  const selectedChunk = chunks.find((chunk) => chunk.key === selectedKey) || null
  const selectedDocumentId = selectedChunk?.documentId

  // 结果读取：选中文档即展示已有 Parse Result（只读）；Run 之后由轮询触发刷新
  const resultQuery = useQuery({
    queryKey: ['parse-result', selectedDocumentId],
    queryFn: async (): Promise<{ result_id: string; data: ParseResult } | null> => {
      try {
        return await parseService.getDocumentParseResult(selectedDocumentId!)
      } catch (error) {
        const status = (error as { response?: { status?: number } })?.response?.status
        if (status === 404) return null
        throw error
      }
    },
    enabled: !!selectedDocumentId,
    retry: false,
    staleTime: 15000,
  })

  const result = resultQuery.data?.data || null
  const pageCount = result?.pages.length || null
  const currentPage: ParsePage | null =
    result?.pages.find((item) => item.page_no === page) || (result?.pages[0] ?? null)

  useEffect(() => {
    setPage(1)
  }, [selectedDocumentId])

  useEffect(() => {
    if (pageCount && page > pageCount) setPage(pageCount)
  }, [pageCount, page])

  // Job 轮询：任一任务在排队/执行中时 1.5s 刷新
  const jobIds = useMemo(
    () => chunks.map((chunk) => chunk.jobId).filter((id): id is string => !!id),
    [chunks],
  )
  const jobsQuery = useQuery({
    queryKey: ['parse-jobs', jobIds.join(',')],
    queryFn: () => Promise.all(jobIds.map((id) => parseService.getJob(id))),
    enabled: jobIds.length > 0,
    refetchInterval: (query) => {
      const jobs = (query.state.data as ProcessingJob[] | undefined) || []
      return jobs.some((job) => job.status === 'queued' || job.status === 'processing') ? 1500 : false
    },
  })

  useEffect(() => {
    const jobs = jobsQuery.data
    if (!jobs || jobs.length === 0) return

    setChunks((prev) =>
      prev.map((chunk) => {
        const job = jobs.find((item) => item.job_id === chunk.jobId)
        if (!job) return chunk
        const nextStatus = jobStatusToChunk(job.status)
        if (nextStatus === chunk.status && (job.error || undefined) === chunk.error) return chunk
        return { ...chunk, status: nextStatus, error: job.error || undefined }
      }),
    )

    const completed = jobs.filter((job) => job.status === 'completed')
    for (const job of completed) {
      const documentId = job.document_ids?.[0]
      if (documentId) {
        void queryClient.invalidateQueries({ queryKey: ['parse-result', documentId] })
      }
    }
  }, [jobsQuery.data, queryClient])

  const restoreJob = useCallback(
    async (jobId: string) => {
      const job = await parseService.getJob(jobId)
      const documentId = job.document_ids?.[0]
      if (!documentId) return
      const status = jobStatusToChunk(job.status)

      setChunks((prev) => {
        const existing = prev.find((chunk) => chunk.documentId === documentId)
        if (existing) {
          return prev.map((chunk) =>
            chunk.documentId === documentId
              ? { ...chunk, jobId, status, error: job.error || undefined }
              : chunk,
          )
        }
        return [
          ...prev,
          {
            key: `restored-${jobId}`,
            name: `文档 ${documentId.slice(0, 8)}`,
            documentId,
            jobId,
            status,
            error: job.error || undefined,
          },
        ]
      })
      const specMode = job.execution_spec?.effective_params?.model_version
      if (specMode === 'pipeline' || specMode === 'vlm') setMode(specMode)
      if (status === 'done') setActiveTab('results')
    },
    [],
  )

  useEffect(() => {
    const jobId = searchParams.get('job')
    if (!jobId || restoreAttempted.current) return
    restoreAttempted.current = true
    void restoreJob(jobId).catch(() => undefined)
  }, [searchParams, restoreJob])

  // 无 job 参数时按 ?doc= 恢复选中文档
  useEffect(() => {
    const docId = searchParams.get('doc')
    if (!docId || docRestoreAttempted.current || chunks.some((c) => c.documentId === docId)) return
    docRestoreAttempted.current = true
    void (async () => {
      try {
        const status = await documentsService.getStatus(docId)
        const key = `restored-doc-${docId}`
        setChunks((prev) =>
          prev.some((c) => c.documentId === docId)
            ? prev
            : [
                ...prev,
                {
                  key,
                  name: status.display_name || status.original_file_name || `文档 ${docId.slice(0, 8)}`,
                  documentId: docId,
                  status: 'ready',
                },
              ],
        )
        setSelectedKey(key)
      } catch {
        // 文档不可用则忽略
      }
    })()
  }, [searchParams, chunks])

  // 选中文档同步到 URL（replace，不新增历史）
  useEffect(() => {
    if (!selectedDocumentId) return
    if (searchParams.get('doc') === selectedDocumentId) return
    const next = new URLSearchParams(searchParams)
    next.set('doc', selectedDocumentId)
    setSearchParams(next, { replace: true })
  }, [selectedDocumentId, searchParams, setSearchParams])

  const handleFiles = async (files: FileList) => {
    const incoming = Array.from(files)
    const newChunks: FileChunk[] = incoming.map((file, index) => ({
      key: `${Date.now()}-${index}-${file.name}`,
      name: file.name,
      status: 'uploading',
    }))
    setChunks((prev) => [...prev, ...newChunks])
    if (!selectedKey && newChunks[0]) setSelectedKey(newChunks[0].key)

    await Promise.all(
      incoming.map(async (file, index) => {
        const key = newChunks[index].key
        try {
          const uploaded = await documentsService.upload(file)
          setChunks((prev) =>
            prev.map((chunk) =>
              chunk.key === key
                ? { ...chunk, status: 'ready', documentId: uploaded.document_id }
                : chunk,
            ),
          )
        } catch (error) {
          setChunks((prev) =>
            prev.map((chunk) =>
              chunk.key === key
                ? { ...chunk, status: 'upload-failed', error: getApiErrorMessage(error, '上传失败') }
                : chunk,
            ),
          )
        }
      }),
    )
  }

  const handleRemoveChunk = (chunk: FileChunk) => {
    if (chunk.status === 'running') {
      const confirmed = window.confirm('该文件仍在解析，移除不会取消任务。确定移除？')
      if (!confirmed) return
    }
    const remaining = chunks.filter((item) => item.key !== chunk.key)
    setChunks(remaining)
    if (selectedKey === chunk.key) setSelectedKey(remaining[0]?.key ?? null)
  }

  const handleRun = async () => {
    const eligible = chunks.filter((chunk) => chunk.documentId)
    if (eligible.length === 0) return

    const reprocessed = eligible.filter((chunk) => chunk.status === 'done' || chunk.status === 'failed')
    if (reprocessed.length > 0) {
      const preview = eligible
        .slice(0, 3)
        .map((chunk) => chunk.name)
        .join('、')
      const more = eligible.length > 3 ? ` 等 ${eligible.length} 个文件` : ''
      const confirmed = window.confirm(
        `将对 ${preview}${more} 重新解析（含 ${reprocessed.length} 个已有结果的文件），继续？`,
      )
      if (!confirmed) return
    }

    setRunError('')
    setRunning(true)
    try {
      const documentIds = eligible
        .map((chunk) => chunk.documentId!)
        .slice()
        .sort()
      const response = await parseService.createJobs({
        document_ids: documentIds,
        parse_mode: mode,
        page_ranges: targetPages.trim() ? { target_pages: targetPages.trim() } : undefined,
      })
      const jobByDocument = new Map(documentIds.map((id, index) => [id, response.job_ids[index]]))
      setChunks((prev) =>
        prev.map((chunk) => {
          const jobId = chunk.documentId ? jobByDocument.get(chunk.documentId) : undefined
          return jobId ? { ...chunk, jobId, status: 'running', error: undefined } : chunk
        }),
      )
      setActiveTab('results')
      void queryClient.invalidateQueries({ queryKey: ['parse-history'] })
    } catch (error) {
      setRunError(getApiErrorMessage(error, '提交解析失败，请稍后重试'))
    } finally {
      setRunning(false)
    }
  }

  const handleOpenHistoryJob = (jobId: string) => {
    setHistoryOpen(false)
    setSearchParams({ job: jobId })
    void restoreJob(jobId).catch(() => undefined)
  }

  const handleCopyPage = async () => {
    if (!currentPage) return
    await navigator.clipboard.writeText(pagePlainText(currentPage))
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  const handleDownloadMarkdown = () => {
    if (!result) return
    const blob = new Blob([resultFullText(result)], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${selectedChunk?.name || 'parse-result'}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  const anyRunning = chunks.some((chunk) => chunk.status === 'running')
  const runningCount = chunks.filter((chunk) => chunk.status === 'running').length
  const doneCount = chunks.filter((chunk) => chunk.status === 'done').length
  const failedCount = chunks.filter((chunk) => chunk.status === 'failed').length
  const announcement = anyRunning
    ? `解析进行中：${runningCount} 个文件`
    : chunks.length > 0 && doneCount + failedCount === chunks.length
      ? `解析结束：成功 ${doneCount}，失败 ${failedCount}`
      : ''

  return (
    <div className="flex h-full text-text-primary">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
        onChange={(event) => {
          if (event.target.files?.length) void handleFiles(event.target.files)
          event.target.value = ''
        }}
      />

      {/* 左栏：文件与原件 */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border-default bg-bg-primary px-4 py-2.5">
          <h1 className="text-sm font-semibold text-text-primary">Parse</h1>
        </div>

        <div className="flex items-center gap-2 border-b border-border-default bg-bg-primary px-3 py-2">
          <Button size="sm" onClick={() => fileInputRef.current?.click()}>
            <Upload className="mr-1 h-4 w-4" />
            Upload
          </Button>
          <span className="text-xs text-text-muted">{chunks.length} file{chunks.length === 1 ? '' : 's'}</span>
          <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto" role="list" aria-label="已上传文件">
            {chunks.map((chunk) => {
              const selected = selectedKey === chunk.key
              return (
                <div
                  key={chunk.key}
                  role="listitem"
                  className={cn(
                    'flex flex-shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
                    selected
                      ? 'border-primary-500/60 bg-primary-500/10 text-text-primary'
                      : 'border-border-default bg-bg-card text-text-secondary hover:bg-bg-hover',
                  )}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedKey(chunk.key)}
                    aria-pressed={selected}
                    title={chunk.error || chunkStatusLabel(chunk.status)}
                    className="flex items-center gap-2"
                  >
                    <StatusDot status={chunk.status} />
                    <span className="max-w-[140px] truncate">{chunk.name}</span>
                    <span className="text-[10px] text-text-muted">{chunkStatusLabel(chunk.status)}</span>
                  </button>
                  <button
                    type="button"
                    aria-label={`移除 ${chunk.name}`}
                    className="rounded p-0.5 text-text-muted hover:text-error-500"
                    onClick={() => handleRemoveChunk(chunk)}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )
            })}
          </div>
        </div>

        <div className="min-h-0 flex-1">
          {selectedChunk?.documentId ? (
            <DocumentPreview
              documentId={selectedChunk.documentId}
              fileName={selectedChunk.name}
              page={page}
              pageCount={pageCount}
              onPageChange={(next) => setPage(Math.max(1, pageCount ? Math.min(next, pageCount) : next))}
            />
          ) : (
            <div
              className="flex h-full flex-col items-center justify-center bg-bg-secondary p-8"
              onDragOver={(event) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                if (event.dataTransfer.files?.length) void handleFiles(event.dataTransfer.files)
              }}
            >
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  'flex w-full max-w-xl flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-8 py-16 transition-colors',
                  dragging
                    ? 'border-primary-500 bg-primary-500/10'
                    : 'border-border-default hover:border-primary-500/50 hover:bg-bg-hover',
                )}
              >
                <Upload className={cn('h-9 w-9', dragging ? 'text-primary-400' : 'text-text-muted')} />
                <span className="text-sm font-medium text-text-primary">
                  {dragging ? '松开即可上传' : '拖拽文件到此处上传'}
                </span>
                <span className="text-xs text-text-muted">或点击选择文件 · PDF / PNG / JPG / TIFF / BMP</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 右栏：Build | Results */}
      <div className="flex w-[440px] flex-shrink-0 flex-col border-l border-border-default bg-bg-card">
        <div className="flex items-center border-b border-border-default">
          <div role="tablist" aria-label="解析配置与结果" className="flex">
            {(['build', 'results'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              id={`parse-tab-${tab}`}
              aria-selected={activeTab === tab}
              aria-controls={`parse-panel-${tab}`}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors',
                activeTab === tab
                  ? 'border-b-2 border-primary-500 text-text-primary'
                  : 'text-text-muted hover:text-text-secondary',
              )}
            >
              {tab === 'build' ? 'Build' : 'Results'}
            </button>
            ))}
          </div>
          <Button
            ref={historyButtonRef}
            variant="ghost"
            size="sm"
            className="ml-auto mr-2"
            onClick={() => setHistoryOpen(true)}
          >
            <History className="mr-1 h-4 w-4" />
            History
          </Button>
        </div>

        {activeTab === 'build' ? (
          <div
            role="tabpanel"
            id="parse-panel-build"
            aria-labelledby="parse-tab-build"
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="flex-1 space-y-5 overflow-auto p-4">
              <div>
                <h3 className="text-sm font-semibold text-text-primary">解析模式</h3>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {(
                    [
                      { value: 'pipeline', label: '快速解析', hint: '文本型文档，低成本' },
                      { value: 'vlm', label: '高精度解析', hint: '扫描件 / 复杂版式' },
                    ] as const
                  ).map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      aria-pressed={mode === option.value}
                      onClick={() => setMode(option.value)}
                      className={cn(
                        'rounded-lg border p-3 text-left transition-colors',
                        mode === option.value
                          ? 'border-primary-500 bg-primary-500/10'
                          : 'border-border-default hover:bg-bg-hover',
                      )}
                    >
                      <p className="text-sm font-medium text-text-primary">{option.label}</p>
                      <p className="mt-1 text-xs text-text-muted">{option.hint}</p>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label htmlFor="target-pages" className="text-sm font-semibold text-text-primary">
                  页码范围（可选）
                </label>
                <Input
                  id="target-pages"
                  className="mt-2"
                  placeholder="例如 1,3,5-10（留空为全部页面）"
                  value={targetPages}
                  onChange={(event) => setTargetPages(event.target.value)}
                />
                <p className="mt-1 text-xs text-text-muted">整批文件使用同一范围；解析范围会记录在任务上</p>
              </div>

              {runError && (
                <p role="alert" className="rounded-lg border border-error-500/30 bg-error-500/10 p-3 text-xs text-error-500">
                  {runError}
                </p>
              )}
            </div>

            <div className="border-t border-border-default p-3">
              <Button
                className="w-full"
                onClick={handleRun}
                disabled={running || anyRunning || chunks.every((chunk) => !chunk.documentId)}
              >
                <Play className="mr-1 h-4 w-4" />
                {anyRunning ? '解析进行中…' : running ? '提交中…' : 'Run Parse'}
              </Button>
            </div>
          </div>
        ) : (
          <div
            role="tabpanel"
            id="parse-panel-results"
            aria-labelledby="parse-tab-results"
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="flex items-center gap-2 border-b border-border-default px-3 py-2">
              <span className="text-xs text-text-muted">
                {result ? `${result.engine?.model_version || 'pipeline'} · ${result.pages.length} 页` : '暂无结果'}
              </span>
              <div className="ml-auto flex items-center gap-1">
                <Button variant="ghost" size="icon-sm" aria-label="上一页" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="min-w-[52px] text-center text-xs tabular-nums">
                  {page}
                  {pageCount ? ` / ${pageCount}` : ''}
                </span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="下一页"
                  disabled={!!pageCount && page >= pageCount}
                  onClick={() => setPage(page + 1)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label="复制当前页" disabled={!currentPage} onClick={handleCopyPage}>
                  {copied ? <Check className="h-4 w-4 text-success-500" /> : <Copy className="h-4 w-4" />}
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label="下载全文 Markdown" disabled={!result} onClick={handleDownloadMarkdown}>
                  <Download className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-auto p-4">
              {!selectedChunk && <p className="py-10 text-center text-sm text-text-muted">选择左侧文件查看结果</p>}
              {selectedChunk?.status === 'failed' && selectedChunk.error && (
                <p
                  role="alert"
                  className="mb-3 rounded-lg border border-error-500/30 bg-error-500/10 p-3 text-xs text-error-500"
                >
                  {selectedChunk.error}
                </p>
              )}
              {selectedChunk && resultQuery.isError && (
                <p
                  role="alert"
                  className="mb-3 rounded-lg border border-error-500/30 bg-error-500/10 p-3 text-xs text-error-500"
                >
                  结果加载失败：{getApiErrorMessage(resultQuery.error, '请稍后重试')}
                </p>
              )}
              {selectedChunk && resultQuery.isLoading && (
                <div className="flex justify-center py-10">
                  <Spinner />
                </div>
              )}
              {selectedChunk && !resultQuery.isLoading && !resultQuery.isError && !result && (
                <p className="py-10 text-center text-sm text-text-muted">
                  {selectedChunk.status === 'running' ? '解析进行中，完成后自动展示' : '该文档还没有解析结果'}
                </p>
              )}
              {selectedChunk?.status === 'done' && !result && !resultQuery.isLoading && (
                <p className="py-2 text-center text-xs text-text-muted">解析已完成，结果同步中…</p>
              )}
              {currentPage && <PageContent page={currentPage} />}
            </div>
          </div>
        )}
      </div>

      <HistoryDrawer
        open={historyOpen}
        currentUser={profile?.user_id}
        returnFocusTo={historyButtonRef}
        onClose={() => setHistoryOpen(false)}
        onOpenJob={handleOpenHistoryJob}
      />

      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
    </div>
  )
}
