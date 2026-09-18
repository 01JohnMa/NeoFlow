import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { documentsService } from '@/services/documents'
import {
  extractService,
  type ExtractEngine,
  type ExtractResultResponse,
} from '@/services/extract'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { CONFIGURATION_STATUS_LABELS, configurationStatusVariant } from '@/lib/configuration'
import { cn, formatDate, getStatusText } from '@/lib/utils'
import type { Document, ProcessingJob } from '@/types'
import { Check, Copy, Download, History, Play, X } from 'lucide-react'

type Tab = 'build' | 'results'

interface ResultSelection {
  documentId: string
  /** 指定时按 Job 读取（History / ?job= 恢复），否则读取文档最新正式结果 */
  jobId?: string
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  const err = error as { response?: { data?: { error?: string; detail?: string } } }
  const detail = err?.response?.data?.error || err?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function getErrorStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } })?.response?.status
}

function jobStatusLabel(status: string): string {
  switch (status) {
    case 'queued':
      return '排队中'
    case 'processing':
      return '抽取中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    default:
      return status
  }
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === 'completed'
      ? 'bg-success-500'
      : status === 'failed'
        ? 'bg-error-500'
        : 'bg-primary-500 animate-pulse'
  return <span className={cn('inline-block h-2 w-2 rounded-full', color)} aria-hidden="true" />
}

function documentName(doc: Document | undefined, fallbackId: string): string {
  if (!doc) return `文档 ${fallbackId.slice(0, 8)}`
  return doc.display_name || doc.original_file_name || doc.file_name || fallbackId
}

function engineSummary(engine?: ExtractEngine | null): string | null {
  if (!engine) return null
  const parts: string[] = []
  if (engine.target) parts.push(`target: ${engine.target}`)
  if (engine.schema_source) parts.push(`schema_source: ${engine.schema_source}`)
  const requests = engine.usage?.requests
  if (typeof requests === 'number') parts.push(`usage.requests: ${requests}`)
  return parts.length ? parts.join(' · ') : null
}

function JsonNode({ name, value, depth }: { name?: string; value: unknown; depth: number }) {
  const pad = { paddingLeft: `${depth * 12}px` }
  const label =
    name === undefined ? null : <span className="text-primary-400">{name}: </span>

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return (
        <div style={pad}>
          {label}
          <span className="text-text-muted">[]</span>
        </div>
      )
    }
    return (
      <div>
        <div style={pad}>
          {label}
          <span className="text-text-secondary">[</span>
        </div>
        {value.map((item, index) => (
          <JsonNode key={index} name={String(index)} value={item} depth={depth + 1} />
        ))}
        <div style={pad}>
          <span className="text-text-secondary">]</span>
        </div>
      </div>
    )
  }

  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) {
      return (
        <div style={pad}>
          {label}
          <span className="text-text-muted">{'{}'}</span>
        </div>
      )
    }
    return (
      <div>
        <div style={pad}>
          {label}
          <span className="text-text-secondary">{'{'}</span>
        </div>
        {entries.map(([key, entry]) => (
          <JsonNode key={key} name={key} value={entry} depth={depth + 1} />
        ))}
        <div style={pad}>
          <span className="text-text-secondary">{'}'}</span>
        </div>
      </div>
    )
  }

  const display =
    value === null ? 'null' : typeof value === 'string' ? JSON.stringify(value) : String(value)
  return (
    <div style={pad}>
      {label}
      <span className={typeof value === 'number' ? 'text-accent-400' : 'text-text-primary'}>
        {display}
      </span>
    </div>
  )
}

function HistoryDrawer({
  open,
  documentNames,
  returnFocusTo,
  onClose,
  onOpenJob,
}: {
  open: boolean
  documentNames: Map<string, string>
  returnFocusTo?: React.RefObject<HTMLButtonElement | null>
  onClose: () => void
  onOpenJob: (jobId: string) => void
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const historyQuery = useQuery({
    queryKey: ['extract-history'],
    queryFn: () => extractService.listJobs({ limit: 50 }),
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

  const jobs = historyQuery.data || []

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="抽取历史">
      <button type="button" aria-label="关闭历史" className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-full max-w-md flex-col border-l border-border-default bg-bg-card">
        <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
          <h2 className="text-sm font-semibold text-text-primary">抽取历史</h2>
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
            <p className="py-10 text-center text-sm text-text-muted">暂无抽取记录</p>
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
                        <StatusDot status={job.status} />
                        {jobStatusLabel(job.status)}
                      </span>
                      <span className="text-xs text-text-muted">{formatDate(job.created_at)}</span>
                    </div>
                    <p className="mt-1 truncate text-xs text-text-secondary">
                      {job.document_ids
                        .map((id) => documentNames.get(id) || `文档 ${id.slice(0, 8)}`)
                        .join('、')}
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

export function ExtractPlayground() {
  const [activeTab, setActiveTab] = useState<Tab>('build')
  const [configId, setConfigId] = useState('')
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const [jobByDoc, setJobByDoc] = useState<Record<string, string>>({})
  const [resultDocIds, setResultDocIds] = useState<string[]>([])
  const [selection, setSelection] = useState<ResultSelection | null>(null)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const historyButtonRef = useRef<HTMLButtonElement>(null)
  const restoreAttempted = useRef(false)
  const queryClient = useQueryClient()

  const configsQuery = useQuery({
    queryKey: ['extract-configs'],
    queryFn: () => extractService.listConfigurations(),
    staleTime: 0,
  })
  const configs = useMemo(() => configsQuery.data || [], [configsQuery.data])
  const selectedConfig = configs.find((config) => config.id === configId) || null

  const documentsQuery = useQuery({
    queryKey: ['extract-documents'],
    queryFn: () => documentsService.list({ page: 1, limit: 50 }),
    staleTime: 15000,
  })
  const documents = useMemo(() => documentsQuery.data?.items || [], [documentsQuery.data])
  const documentById = useMemo(
    () => new Map(documents.map((doc) => [doc.id, doc])),
    [documents],
  )
  const documentNames = useMemo(
    () => new Map(documents.map((doc) => [doc.id, documentName(doc, doc.id)])),
    [documents],
  )

  // 默认选中首个可用配置
  useEffect(() => {
    if (configs.length === 0) return
    setConfigId((prev) => (prev && configs.some((config) => config.id === prev) ? prev : configs[0].id))
  }, [configs])

  // Job 轮询：任一任务排队/执行中时 1.5s 刷新
  const jobIds = useMemo(() => Object.values(jobByDoc), [jobByDoc])
  const jobsQuery = useQuery({
    queryKey: ['extract-jobs', jobIds.join(',')],
    queryFn: () => Promise.all(jobIds.map((id) => extractService.getJob(id))),
    enabled: jobIds.length > 0,
    refetchInterval: (query) => {
      const jobs = (query.state.data as ProcessingJob[] | undefined) || []
      return jobs.some((job) => job.status === 'queued' || job.status === 'processing')
        ? 1500
        : false
    },
  })
  const jobsByDocument = useMemo(() => {
    const map = new Map<string, ProcessingJob>()
    for (const job of jobsQuery.data || []) {
      const documentId = job.document_ids?.[0]
      if (documentId) map.set(documentId, job)
    }
    return map
  }, [jobsQuery.data])

  useEffect(() => {
    for (const job of jobsQuery.data || []) {
      if (job.status !== 'completed') continue
      const documentId = job.document_ids?.[0]
      if (documentId) {
        void queryClient.invalidateQueries({ queryKey: ['extract-result', documentId] })
      }
    }
  }, [jobsQuery.data, queryClient])

  const selectedDocumentId = selection?.documentId
  const selectedJobId = selection?.jobId
  const resultQuery = useQuery({
    queryKey: ['extract-result', selectedDocumentId, selectedJobId],
    queryFn: async (): Promise<ExtractResultResponse | null> => {
      if (!selection) return null
      try {
        return selection.jobId
          ? await extractService.getJobResult(selection.jobId)
          : await extractService.getDocumentResult(selection.documentId)
      } catch (error) {
        if (getErrorStatus(error) === 404) return null
        throw error
      }
    },
    enabled: !!selection,
    retry: false,
    staleTime: 15000,
  })
  const result = resultQuery.data || null

  // ?job=<id> 恢复：读取该 Job 的正式结果
  useEffect(() => {
    const jobId = searchParams.get('job')
    if (!jobId || restoreAttempted.current) return
    restoreAttempted.current = true
    void (async () => {
      try {
        const job = await extractService.getJob(jobId)
        const documentId = job.document_ids?.[0]
        if (!documentId) return
        setJobByDoc((prev) => ({ ...prev, [documentId]: jobId }))
        setResultDocIds((prev) => (prev.includes(documentId) ? prev : [...prev, documentId]))
        setSelection({ documentId, jobId })
        setActiveTab('results')
      } catch {
        // 任务不可用则忽略
      }
    })()
  }, [searchParams])

  const toggleDoc = (documentId: string) => {
    setSelectedDocIds((prev) =>
      prev.includes(documentId)
        ? prev.filter((id) => id !== documentId)
        : [...prev, documentId],
    )
  }

  const allSelected =
    documents.length > 0 && documents.every((doc) => selectedDocIds.includes(doc.id))
  const toggleAll = () => {
    setSelectedDocIds(allSelected ? [] : documents.map((doc) => doc.id))
  }

  const handleRun = async () => {
    if (!configId || selectedDocIds.length === 0) return
    setRunError('')
    setRunning(true)
    try {
      const documentIds = [...selectedDocIds].sort()
      const response = await extractService.createJobs({
        configuration_id: configId,
        document_ids: documentIds,
      })
      const nextJobs: Record<string, string> = {}
      documentIds.forEach((documentId, index) => {
        const jobId = response.job_ids[index]
        if (jobId) nextJobs[documentId] = jobId
      })
      setJobByDoc((prev) => ({ ...prev, ...nextJobs }))
      setResultDocIds(documentIds)
      setSelection({ documentId: documentIds[0] })
      setActiveTab('results')
      void queryClient.invalidateQueries({ queryKey: ['extract-history'] })
    } catch (error) {
      setRunError(getApiErrorMessage(error, '提交抽取失败，请稍后重试'))
    } finally {
      setRunning(false)
    }
  }

  const openHistoryJob = (jobId: string) => {
    setHistoryOpen(false)
    setSearchParams({ job: jobId })
    void (async () => {
      try {
        const job = await extractService.getJob(jobId)
        const documentId = job.document_ids?.[0]
        if (!documentId) return
        setJobByDoc((prev) => ({ ...prev, [documentId]: jobId }))
        setResultDocIds((prev) => (prev.includes(documentId) ? prev : [...prev, documentId]))
        setSelection({ documentId, jobId })
        setActiveTab('results')
      } catch {
        // 任务不可用则忽略
      }
    })()
  }

  const handleCopy = async () => {
    if (!result) return
    await navigator.clipboard.writeText(JSON.stringify(result.data, null, 2))
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  const handleDownload = () => {
    if (!result) return
    const baseName = selectedDocumentId
      ? documentName(documentById.get(selectedDocumentId), selectedDocumentId)
      : 'extract-result'
    const safeName = baseName.replace(/[\\/:*?"<>|]/g, '_')
    const blob = new Blob([JSON.stringify(result.data, null, 2)], {
      type: 'application/json;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${safeName}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const selectedJob = selectedDocumentId ? jobsByDocument.get(selectedDocumentId) : undefined
  const summary = result ? engineSummary(result.engine) : null

  return (
    <div className="flex h-full flex-col text-text-primary">
      <div className="flex items-center gap-4 border-b border-border-default bg-bg-primary px-4 py-2.5">
        <h1 className="text-sm font-semibold text-text-primary">Extract</h1>
        <div role="tablist" aria-label="抽取配置与结果" className="flex">
          {(['build', 'results'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              id={`extract-tab-${tab}`}
              aria-selected={activeTab === tab}
              aria-controls={`extract-panel-${tab}`}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors',
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
          className="ml-auto"
          onClick={() => setHistoryOpen(true)}
        >
          <History className="mr-1 h-4 w-4" />
          History
        </Button>
      </div>

      {activeTab === 'build' ? (
        <div
          role="tabpanel"
          id="extract-panel-build"
          aria-labelledby="extract-tab-build"
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="flex-1 overflow-auto p-4">
            <div className="mx-auto w-full max-w-3xl space-y-5">
              <div>
                <label htmlFor="extract-config" className="text-sm font-semibold text-text-primary">
                  抽取配置
                </label>
                {configsQuery.isLoading ? (
                  <div className="mt-2 flex justify-center py-4">
                    <Spinner />
                  </div>
                ) : configsQuery.isError ? (
                  <div className="mt-2 flex items-center gap-3 rounded-lg border border-error-500/30 bg-error-500/10 p-3 text-xs text-error-500">
                    <span>配置加载失败：{getApiErrorMessage(configsQuery.error, '请稍后重试')}</span>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="ml-auto"
                      onClick={() => void configsQuery.refetch()}
                    >
                      重试
                    </Button>
                  </div>
                ) : configs.length === 0 ? (
                  <p className="mt-2 rounded-lg border border-border-default bg-bg-secondary p-3 text-xs text-text-muted">
                    暂无可用的 Extract 配置，请联系管理员
                  </p>
                ) : (
                  <>
                    <div className="mt-2 flex items-center gap-2">
                      <Select
                        id="extract-config"
                        value={configId}
                        onChange={(event) => setConfigId(event.target.value)}
                      >
                        <option value="" disabled>
                          选择配置
                        </option>
                        {configs.map((config) => (
                          <option key={config.id} value={config.id}>
                            {config.name}
                          </option>
                        ))}
                      </Select>
                      {selectedConfig && (
                        <Badge variant={configurationStatusVariant(selectedConfig.status)}>
                          {CONFIGURATION_STATUS_LABELS[selectedConfig.status]}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-3">
                      {selectedConfig?.draft_definition?.data_schema ? (
                        <pre className="max-h-40 overflow-auto rounded-lg border border-border-default bg-bg-secondary p-3 font-mono text-[11px] leading-relaxed text-text-secondary">
                          {JSON.stringify(selectedConfig.draft_definition.data_schema, null, 2)}
                        </pre>
                      ) : (
                        <p className="rounded-lg border border-border-default bg-bg-secondary p-3 text-xs text-text-muted">
                          旧版配置：运行时按字段自动转换（
                          {selectedConfig?.draft_definition?.fields?.length ?? 0} 个字段）
                        </p>
                      )}
                    </div>
                  </>
                )}
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-text-primary">选择文档</h3>
                  <span className="text-xs text-text-muted">
                    已选 {selectedDocIds.length} / {documents.length}
                  </span>
                </div>
                {documentsQuery.isLoading ? (
                  <div className="mt-2 flex justify-center py-4">
                    <Spinner />
                  </div>
                ) : documentsQuery.isError ? (
                  <div className="mt-2 flex items-center gap-3 rounded-lg border border-error-500/30 bg-error-500/10 p-3 text-xs text-error-500">
                    <span>文档加载失败：{getApiErrorMessage(documentsQuery.error, '请稍后重试')}</span>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="ml-auto"
                      onClick={() => void documentsQuery.refetch()}
                    >
                      重试
                    </Button>
                  </div>
                ) : documents.length === 0 ? (
                  <p className="mt-2 rounded-lg border border-border-default bg-bg-secondary p-3 text-xs text-text-muted">
                    暂无文档，请先上传
                  </p>
                ) : (
                  <>
                    <label className="mt-2 flex cursor-pointer items-center gap-2 rounded-lg border border-border-default px-3 py-2 text-xs text-text-secondary transition-colors hover:bg-bg-hover">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={toggleAll}
                        className="rounded"
                      />
                      全选
                    </label>
                    <ul className="mt-2 max-h-72 space-y-1 overflow-auto">
                      {documents.map((doc) => {
                        const checked = selectedDocIds.includes(doc.id)
                        return (
                          <li key={doc.id}>
                            <label
                              className={cn(
                                'flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition-colors',
                                checked
                                  ? 'border-primary-500/60 bg-primary-500/10'
                                  : 'border-border-default hover:bg-bg-hover',
                              )}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleDoc(doc.id)}
                                className="rounded"
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm text-text-primary">
                                  {documentName(doc, doc.id)}
                                </span>
                                <span className="mt-0.5 block text-xs text-text-muted">
                                  {getStatusText(doc.status)} · {formatDate(doc.created_at)}
                                </span>
                              </span>
                            </label>
                          </li>
                        )
                      })}
                    </ul>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="border-t border-border-default p-3">
            <div className="mx-auto w-full max-w-3xl">
              {runError && (
                <p
                  role="alert"
                  className="mb-2 rounded-lg border border-error-500/30 bg-error-500/10 p-3 text-xs text-error-500"
                >
                  {runError}
                </p>
              )}
              <Button
                className="w-full"
                onClick={handleRun}
                disabled={running || !configId || selectedDocIds.length === 0}
              >
                <Play className="mr-1 h-4 w-4" />
                {running ? '提交中…' : 'Run Extract'}
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div
          role="tabpanel"
          id="extract-panel-results"
          aria-labelledby="extract-tab-results"
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="flex items-center gap-2 border-b border-border-default px-4 py-2">
            <div
              className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto"
              role="list"
              aria-label="本次运行的文档"
            >
              {resultDocIds.map((documentId) => {
                const active = selection?.documentId === documentId
                return (
                  <button
                    key={documentId}
                    type="button"
                    role="listitem"
                    aria-pressed={active}
                    onClick={() => setSelection({ documentId })}
                    className={cn(
                      'flex-shrink-0 rounded-md border px-2.5 py-1 text-xs transition-colors',
                      active
                        ? 'border-primary-500/60 bg-primary-500/10 text-text-primary'
                        : 'border-border-default bg-bg-card text-text-secondary hover:bg-bg-hover',
                    )}
                  >
                    <span className="block max-w-[180px] truncate">
                      {documentName(documentById.get(documentId), documentId)}
                    </span>
                  </button>
                )
              })}
              {resultDocIds.length === 0 && (
                <span className="text-xs text-text-muted">暂无本次运行的文档</span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="复制 JSON"
                disabled={!result}
                onClick={() => void handleCopy()}
              >
                {copied ? <Check className="h-4 w-4 text-success-500" /> : <Copy className="h-4 w-4" />}
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="下载 JSON"
                disabled={!result}
                onClick={handleDownload}
              >
                <Download className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto p-4">
            {resultDocIds.length === 0 && (
              <p className="py-10 text-center text-sm text-text-muted">
                提交抽取任务后可在此查看结果
              </p>
            )}
            {resultDocIds.length > 0 && !selection && (
              <p className="py-10 text-center text-sm text-text-muted">选择上方文档查看抽取结果</p>
            )}
            {selection && selectedJob?.status === 'failed' && selectedJob.error && (
              <p
                role="alert"
                className="mb-3 rounded-lg border border-error-500/30 bg-error-500/10 p-3 text-xs text-error-500"
              >
                {selectedJob.error}
              </p>
            )}
            {selection && resultQuery.isError && (
              <p
                role="alert"
                className="mb-3 rounded-lg border border-error-500/30 bg-error-500/10 p-3 text-xs text-error-500"
              >
                结果加载失败：{getApiErrorMessage(resultQuery.error, '请稍后重试')}
              </p>
            )}
            {selection && resultQuery.isLoading && (
              <div className="flex justify-center py-10">
                <Spinner />
              </div>
            )}
            {selection && !resultQuery.isLoading && !resultQuery.isError && !result && (
              <p className="py-10 text-center text-sm text-text-muted">
                {selection.jobId
                  ? '该任务没有正式结果（失败或进行中）'
                  : selectedJob?.status === 'queued' || selectedJob?.status === 'processing'
                    ? '抽取进行中，完成后自动展示'
                    : '该文档还没有抽取结果'}
              </p>
            )}
            {result && (
              <>
                {summary && <p className="mb-2 text-xs text-text-muted">{summary}</p>}
                <div className="overflow-auto rounded-lg border border-border-default bg-bg-secondary p-3 font-mono text-xs leading-relaxed">
                  <JsonNode value={result.data} depth={0} />
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <HistoryDrawer
        open={historyOpen}
        documentNames={documentNames}
        returnFocusTo={historyButtonRef}
        onClose={() => setHistoryOpen(false)}
        onOpenJob={openHistoryJob}
      />
    </div>
  )
}

export default ExtractPlayground
