import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useJob, useParseResult } from '@/hooks/useJobs'
import { documentKeys } from '@/hooks/useDocuments'
import { documentsService } from '@/services/documents'
import { PagePreview } from '@/components/parse/PagePreview'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { cn, formatDate, getStatusColor, getStatusText } from '@/lib/utils'
import {
  formatConfidence,
  getBlockTypeLabel,
  getJobPhase,
  getJobStageLabel,
  getSourceBadgeClass,
  getSourceHint,
  getSourceLabel,
  parseMarkdown,
  type MarkdownBlock,
} from '@/lib/parseViewer'
import type { Document, ParseBlock, ParseResult, ProcessingJob } from '@/types'
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  FileSearch,
  RefreshCw,
  Search,
} from 'lucide-react'

function getApiErrorMessage(error: unknown, fallback: string): string {
  const err = error as { response?: { data?: { error?: string; detail?: string } } }
  const detail = err?.response?.data?.error || err?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function JobIdForm({
  initialJobId,
  onSubmit,
}: {
  initialJobId: string
  onSubmit: (jobId: string) => void
}) {
  const [value, setValue] = useState(initialJobId)

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(value.trim())
      }}
      className="flex w-full gap-2 md:w-auto"
    >
      <Input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="输入 Parse Job ID"
        className="md:w-80"
        aria-label="Parse Job ID"
      />
      <Button type="submit" className="flex-shrink-0">
        <Search className="mr-2 h-4 w-4" />
        查看
      </Button>
    </form>
  )
}

function MarkdownBlockView({ block }: { block: MarkdownBlock }) {
  switch (block.kind) {
    case 'heading': {
      const sizeClass =
        block.level === 1
          ? 'text-xl font-bold'
          : block.level === 2
            ? 'text-lg font-semibold'
            : 'text-base font-semibold'
      return <p className={cn('text-text-primary', sizeClass)}>{block.text}</p>
    }
    case 'paragraph':
      return (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-text-secondary">
          {block.text}
        </p>
      )
    case 'list': {
      const ListTag = block.ordered ? 'ol' : 'ul'
      return (
        <ListTag
          className={cn(
            'space-y-1 pl-5 text-sm text-text-secondary',
            block.ordered ? 'list-decimal' : 'list-disc',
          )}
        >
          {block.items.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ListTag>
      )
    }
    case 'table':
      return (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border-default text-left text-text-primary">
                {block.header.map((cell, index) => (
                  <th key={index} className="px-3 py-2 font-medium">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-b border-border-default/50">
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className="px-3 py-2 text-text-secondary">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    case 'code':
      return (
        <pre className="overflow-x-auto rounded-lg bg-bg-secondary p-3 text-xs text-text-secondary">
          <code>{block.text}</code>
        </pre>
      )
    case 'image':
      return (
        <p className="text-xs text-text-muted">[图片] {block.alt || '（无描述）'}</p>
      )
  }
}

function MarkdownPreview({ markdown }: { markdown: string | null }) {
  const blocks = useMemo(() => parseMarkdown(markdown), [markdown])
  if (blocks.length === 0) {
    return <p className="text-sm text-text-muted">本页没有 markdown 内容</p>
  }
  return (
    <div className="space-y-3">
      {blocks.map((block, index) => (
        <MarkdownBlockView key={index} block={block} />
      ))}
    </div>
  )
}

function BlockDetails({ block }: { block: ParseBlock }) {
  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{getBlockTypeLabel(block.type)}</Badge>
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
            getSourceBadgeClass(block.source),
          )}
        >
          {getSourceLabel(block.source)}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-3">
        <div>
          <dt className="text-xs text-text-muted">阅读顺序</dt>
          <dd className="mt-0.5 text-text-primary">第 {block.reading_order} 位</dd>
        </div>
        <div>
          <dt className="text-xs text-text-muted">置信度</dt>
          <dd
            className={cn(
              'mt-0.5',
              block.source === 'vlm' || block.confidence === null
                ? 'text-warning-500'
                : 'text-text-primary',
            )}
          >
            {formatConfidence(block.source, block.confidence)}
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="text-xs text-text-muted">坐标 bbox</dt>
          <dd className="mt-0.5 font-mono text-xs text-text-secondary">
            {block.bbox.length > 0 ? block.bbox.join(', ') : '-'}
          </dd>
        </div>
      </dl>

      {getSourceHint(block.source) && (
        <p className="text-xs text-text-muted">{getSourceHint(block.source)}</p>
      )}

      {block.text && (
        <div>
          <p className="text-xs text-text-muted">文本</p>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-bg-secondary p-3 text-xs text-text-secondary">
            {block.text}
          </pre>
        </div>
      )}

      {block.table_html && (
        <div>
          <p className="text-xs text-text-muted">表格 HTML</p>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-bg-secondary p-3 text-xs text-text-secondary">
            {block.table_html}
          </pre>
        </div>
      )}

      {block.latex && (
        <div>
          <p className="text-xs text-text-muted">LaTeX</p>
          <pre className="mt-1 overflow-auto rounded-lg bg-bg-secondary p-3 text-xs text-text-secondary">
            {block.latex}
          </pre>
        </div>
      )}

      {block.image_path && (
        <p className="break-all text-xs text-text-muted">图片路径：{block.image_path}</p>
      )}
    </div>
  )
}

function JobStatusCard({ job }: { job: ProcessingJob }) {
  const phase = getJobPhase(job)
  const progress = Math.max(0, Math.min(100, job.progress ?? 0))

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex flex-wrap items-center gap-3">
          <Badge className={getStatusColor(job.status)}>{getStatusText(job.status)}</Badge>
          {phase === 'running' && (
            <>
              <span className="text-sm text-text-secondary">
                当前阶段：{getJobStageLabel(job.stage)}
              </span>
              <Spinner size="sm" />
            </>
          )}
          <span className="ml-auto text-xs text-text-muted">
            任务 {job.job_id} · 更新于 {formatDate(job.updated_at)}
          </span>
        </div>

        {phase === 'running' && (
          <>
            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-bg-secondary">
              <div
                className="h-full rounded-full bg-primary-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="mt-3 text-sm text-text-muted">
              解析任务执行中，页面会自动刷新状态，请勿重复提交。
            </p>
          </>
        )}

        {phase === 'failed' && (
          <div className="mt-4 flex items-start gap-3 rounded-lg border border-error-500/20 bg-error-500/10 p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-error-500" />
            <div>
              <p className="font-medium text-error-500">解析失败</p>
              <p className="mt-1 text-sm text-text-secondary">
                {job.error || '任务执行失败，未返回错误详情'}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ParseResultPanel({
  result,
  document,
}: {
  result: ParseResult
  document?: Document
}) {
  const pages = result.pages
  const [pageNo, setPageNo] = useState(pages[0]?.page_no ?? 1)
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null)
  const [showOverlays, setShowOverlays] = useState(true)

  const pageIndex = pages.findIndex((page) => page.page_no === pageNo)
  const resolvedIndex = pageIndex >= 0 ? pageIndex : 0
  const currentPage = pages[resolvedIndex]
  const selectedBlock =
    currentPage?.blocks.find((block) => block.id === selectedBlockId) ?? null

  const goToPage = (index: number) => {
    if (index < 0 || index >= pages.length) return
    setPageNo(pages[index].page_no)
    setSelectedBlockId(null)
  }

  if (!currentPage) return null

  return (
    <>
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-3">
            <Select
              value={String(currentPage.page_no)}
              onChange={(event) => goToPage(Number(event.target.value) - 1)}
              className="w-40"
              aria-label="选择页面"
            >
              {pages.map((page) => (
                <option key={page.page_no} value={page.page_no}>
                  第 {page.page_no} 页（{page.blocks.length} 块）
                </option>
              ))}
            </Select>
            <Button
              variant="outline"
              size="sm"
              onClick={() => goToPage(resolvedIndex - 1)}
              disabled={resolvedIndex <= 0}
            >
              <ChevronLeft className="h-4 w-4" />
              上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => goToPage(resolvedIndex + 1)}
              disabled={resolvedIndex >= pages.length - 1}
            >
              下一页
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowOverlays((value) => !value)}
            >
              {showOverlays ? (
                <EyeOff className="mr-2 h-4 w-4" />
              ) : (
                <Eye className="mr-2 h-4 w-4" />
              )}
              {showOverlays ? '隐藏坐标框' : '显示坐标框'}
            </Button>
            <span className="ml-auto text-xs text-text-muted">
              共 {pages.length} 页 / {pages.reduce((sum, page) => sum + page.blocks.length, 0)}{' '}
              块
            </span>
          </div>

          {result.engine && Object.keys(result.engine).length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-text-muted">
              <span>引擎：</span>
              <span className="text-text-secondary">
                {[
                  result.engine.name,
                  result.engine.backend,
                  result.engine.effort ? `effort=${result.engine.effort}` : '',
                  result.engine.version,
                ]
                  .filter(Boolean)
                  .join(' / ') || '未知'}
              </span>
            </div>
          )}

          {result.warnings.length > 0 && (
            <div className="mt-3 rounded-lg border border-warning-500/20 bg-warning-500/10 p-3">
              <p className="flex items-center gap-2 text-sm font-medium text-warning-500">
                <AlertTriangle className="h-4 w-4" />
                解析警告（{result.warnings.length}）
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-text-secondary">
                {result.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="pb-4">
            <CardTitle className="text-base">
              第 {currentPage.page_no} 页
              <span className="ml-2 text-xs font-normal text-text-muted">
                {currentPage.width} × {currentPage.height}
                {currentPage.coordinate_space === 'normalized-1000'
                  ? '（归一化坐标）'
                  : ' 像素'}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <PagePreview
              key={document?.id ?? 'no-document'}
              page={currentPage}
              document={document}
              selectedBlockId={selectedBlockId}
              onSelectBlock={setSelectedBlockId}
              showOverlays={showOverlays}
            />
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-base">
                块列表（{currentPage.blocks.length}）
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-0">
              {currentPage.blocks.length === 0 ? (
                <p className="px-3 py-6 text-center text-sm text-text-muted">
                  本页没有解析块
                </p>
              ) : (
                <div className="max-h-[32rem] space-y-1 overflow-y-auto">
                  {[...currentPage.blocks]
                    .sort((a, b) => a.reading_order - b.reading_order)
                    .map((block) => {
                      const selected = block.id === selectedBlockId
                      return (
                        <button
                          key={block.id}
                          type="button"
                          onClick={() => setSelectedBlockId(block.id)}
                          className={cn(
                            'w-full rounded-lg border px-3 py-2 text-left transition-colors',
                            selected
                              ? 'border-primary-500 bg-primary-500/10'
                              : 'border-transparent hover:bg-bg-hover',
                          )}
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs text-text-muted">
                              #{block.reading_order}
                            </span>
                            <Badge variant="secondary">
                              {getBlockTypeLabel(block.type)}
                            </Badge>
                            <span
                              className={cn(
                                'rounded-full px-2 py-0.5 text-[11px] font-medium',
                                getSourceBadgeClass(block.source),
                              )}
                            >
                              {getSourceLabel(block.source)}
                            </span>
                            <span className="ml-auto text-xs text-text-muted">
                              {formatConfidence(block.source, block.confidence)}
                            </span>
                          </div>
                          {block.text && (
                            <p className="mt-1 line-clamp-2 text-sm text-text-secondary">
                              {block.text}
                            </p>
                          )}
                        </button>
                      )
                    })}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-base">块详情</CardTitle>
            </CardHeader>
            <CardContent>
              {selectedBlock ? (
                <BlockDetails block={selectedBlock} />
              ) : (
                <p className="text-sm text-text-muted">
                  点击页面坐标框或块列表查看详情
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">页面 Markdown</CardTitle>
          <CardDescription>第 {currentPage.page_no} 页解析文本</CardDescription>
        </CardHeader>
        <CardContent>
          <MarkdownPreview markdown={currentPage.markdown} />
        </CardContent>
      </Card>
    </>
  )
}

export function ParseViewer() {
  const [searchParams, setSearchParams] = useSearchParams()
  const jobId = searchParams.get('job')?.trim() || ''

  const jobQuery = useJob(jobId || undefined)
  const job = jobQuery.data
  const phase = jobId ? getJobPhase(job) : 'idle'

  const documentId = job?.document_ids?.[0]
  const { data: document } = useQuery({
    queryKey: documentKeys.detail(documentId ?? ''),
    queryFn: () => documentsService.get(documentId!),
    enabled: !!documentId,
  })

  const resultQuery = useParseResult(jobId || undefined, phase === 'completed')
  const result = resultQuery.data

  const handleJobSubmit = (value: string) => {
    if (value) {
      setSearchParams({ job: value })
    } else {
      setSearchParams({})
    }
  }

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-text-primary">解析结果查看器</h2>
          <p className="mt-1 text-text-secondary">
            按页查看解析 markdown，点选块核对坐标、类型、来源与置信度
          </p>
        </div>
        <JobIdForm
          key={jobId}
          initialJobId={jobId}
          onSubmit={handleJobSubmit}
        />
      </div>

      {!jobId && (
        <Card>
          <CardContent className="py-12 text-center">
            <FileSearch className="mx-auto mb-4 h-12 w-12 text-text-muted" />
            <p className="text-text-primary">请输入 Parse Job ID</p>
            <p className="mt-1 text-sm text-text-muted">
              解析任务完成后，可在任务详情或接口返回值中获取 Job ID
            </p>
          </CardContent>
        </Card>
      )}

      {jobId && jobQuery.isLoading && (
        <Card>
          <CardContent className="flex justify-center py-12">
            <Spinner />
          </CardContent>
        </Card>
      )}

      {jobId && jobQuery.isError && (
        <Card>
          <CardContent className="py-12 text-center">
            <AlertTriangle className="mx-auto mb-4 h-12 w-12 text-warning-500" />
            <p className="text-text-primary">无法读取任务</p>
            <p className="mt-1 text-sm text-text-muted">
              {getApiErrorMessage(jobQuery.error, '任务不存在或无权访问')}
            </p>
          </CardContent>
        </Card>
      )}

      {job && (
        <>
          <Card>
            <CardHeader className="pb-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <CardTitle className="truncate text-lg">
                    {document?.display_name ||
                      document?.original_file_name ||
                      document?.file_name ||
                      '未关联文档'}
                  </CardTitle>
                  <CardDescription>
                    任务 {job.job_id} · 创建于 {formatDate(job.created_at)}
                  </CardDescription>
                </div>
                <Badge className={getStatusColor(job.status)}>
                  {getStatusText(job.status)}
                </Badge>
              </div>
            </CardHeader>
          </Card>

          {(phase === 'running' || phase === 'failed') && <JobStatusCard job={job} />}

          {phase === 'completed' && resultQuery.isLoading && (
            <Card>
              <CardContent className="flex justify-center py-12">
                <Spinner />
              </CardContent>
            </Card>
          )}

          {phase === 'completed' && resultQuery.isError && (
            <Card>
              <CardContent className="py-12 text-center">
                <AlertTriangle className="mx-auto mb-4 h-12 w-12 text-warning-500" />
                <p className="text-text-primary">解析结果不可用</p>
                <p className="mt-1 text-sm text-text-muted">
                  {getApiErrorMessage(resultQuery.error, '解析结果不存在或尚未写入')}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4"
                  onClick={() => resultQuery.refetch()}
                  disabled={resultQuery.isFetching}
                >
                  <RefreshCw
                    className={cn('mr-2 h-4 w-4', resultQuery.isFetching && 'animate-spin')}
                  />
                  重新获取
                </Button>
              </CardContent>
            </Card>
          )}

          {phase === 'completed' && result && result.pages.length === 0 && (
            <Card>
              <CardContent className="py-12 text-center">
                <FileSearch className="mx-auto mb-4 h-12 w-12 text-text-muted" />
                <p className="text-text-primary">解析结果没有页面</p>
                <p className="mt-1 text-sm text-text-muted">
                  该 ParseResult 的 pages 为空，请检查解析任务输出
                </p>
              </CardContent>
            </Card>
          )}

          {phase === 'completed' && result && result.pages.length > 0 && (
            <ParseResultPanel key={jobId} result={result} document={document} />
          )}
        </>
      )}
    </div>
  )
}
