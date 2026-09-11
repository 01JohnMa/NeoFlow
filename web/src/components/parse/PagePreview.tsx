import { useEffect, useState } from 'react'
import { documentsService } from '@/services/documents'
import { cn } from '@/lib/utils'
import {
  bboxToOverlayRect,
  getBlockTypeLabel,
  getSourceLabel,
  getSourceOverlayClass,
  resolveDocumentPreviewKind,
} from '@/lib/parseViewer'
import { Spinner } from '@/components/ui/spinner'
import type { Document, ParsePage } from '@/types'

interface PagePreviewProps {
  page: ParsePage
  document?: Document
  selectedBlockId: string | null
  onSelectBlock: (blockId: string) => void
  showOverlays: boolean
}

export function PagePreview({
  page,
  document,
  selectedBlockId,
  onSelectBlock,
  showOverlays,
}: PagePreviewProps) {
  const kind = resolveDocumentPreviewKind(document)
  const documentId = document?.id
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [previewFailed, setPreviewFailed] = useState(false)

  useEffect(() => {
    if (!documentId || kind === 'unsupported') return

    let cancelled = false
    let objectUrl: string | null = null

    documentsService
      .fetchFileBlob(documentId)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setBlobUrl(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setPreviewFailed(true)
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [documentId, kind])

  const aspectRatio =
    page.width > 0 && page.height > 0 ? `${page.width} / ${page.height}` : '3 / 4'

  return (
    <div className="space-y-2">
      <div
        className="relative w-full overflow-hidden rounded-lg border border-border-default bg-bg-secondary"
        style={{ aspectRatio }}
      >
        {kind === 'image' && blobUrl && (
          <img
            src={blobUrl}
            alt={`第 ${page.page_no} 页页面`}
            className="block h-full w-full select-none object-contain"
            draggable={false}
            onError={() => setPreviewFailed(true)}
          />
        )}

        {kind === 'pdf' && blobUrl && (
          <iframe
            src={`${blobUrl}#page=${page.page_no}&zoom=page-width`}
            title={`第 ${page.page_no} 页 PDF`}
            className="h-full w-full"
          />
        )}

        {kind === 'unsupported' && (
          <div
            className="flex h-full w-full items-center justify-center"
            style={{
              backgroundImage:
                'linear-gradient(to right, rgba(148,163,184,0.12) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.12) 1px, transparent 1px)',
              backgroundSize: '10% 8%',
            }}
          >
            <p className="px-6 text-center text-sm text-text-muted">
              该文档类型没有可直接预览的页面图像，以下按解析坐标示意
            </p>
          </div>
        )}

        {kind !== 'unsupported' && !blobUrl && !previewFailed && (
          <div className="flex h-full w-full items-center justify-center">
            <Spinner />
          </div>
        )}

        {previewFailed && kind !== 'unsupported' && (
          <div className="flex h-full w-full items-center justify-center">
            <p className="px-6 text-center text-sm text-text-muted">
              页面预览加载失败，仍可查看右侧块列表与 markdown
            </p>
          </div>
        )}

        {showOverlays &&
          page.blocks.map((block) => {
            const rect = bboxToOverlayRect(block.bbox, page)
            if (!rect) return null
            const selected = block.id === selectedBlockId
            const label = getBlockTypeLabel(block.type)
            const source = getSourceLabel(block.source)

            return (
              <button
                key={block.id}
                type="button"
                aria-label={`${label} 来源 ${source}，阅读顺序 ${block.reading_order}`}
                title={`${label} · ${source} · 阅读顺序 ${block.reading_order}`}
                onClick={() => onSelectBlock(block.id)}
                className={cn(
                  'absolute rounded-sm border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
                  getSourceOverlayClass(block.source),
                  selected
                    ? 'z-20 border-primary-400 bg-primary-500/30 shadow-lg shadow-primary-500/30'
                    : 'z-10 hover:bg-primary-500/20',
                )}
                style={{
                  left: `${rect.left}%`,
                  top: `${rect.top}%`,
                  width: `${rect.width}%`,
                  height: `${rect.height}%`,
                }}
              >
                {selected && (
                  <span className="absolute -top-6 left-0 z-30 whitespace-nowrap rounded bg-primary-500 px-1.5 py-0.5 text-[10px] font-medium text-white">
                    {label}
                  </span>
                )}
              </button>
            )
          })}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
        {(['native-text', 'ocr', 'vlm', 'office-xml'] as const).map((source) => (
          <span key={source} className="flex items-center gap-1.5">
            <span
              className={cn('inline-block h-3 w-3 rounded-sm border-2', getSourceOverlayClass(source))}
            />
            {getSourceLabel(source)}
          </span>
        ))}
        <span className="ml-auto">
          页面坐标空间：{page.coordinate_space === 'pixel' ? '像素' : page.coordinate_space}
        </span>
      </div>
    </div>
  )
}
