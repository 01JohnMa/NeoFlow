import type { ParseBlockType, ParseSource, ProcessingJob } from '@/types'

// ============ 块类型 / 来源标签 ============

const BLOCK_TYPE_LABELS: Record<ParseBlockType, string> = {
  title: '标题',
  text: '正文',
  list: '列表',
  table: '表格',
  figure: '图片',
  formula: '公式',
  header: '页眉',
  footer: '页脚',
}

const SOURCE_LABELS: Record<ParseSource, string> = {
  'native-text': '文字层',
  ocr: 'OCR',
  vlm: 'VLM',
  'office-xml': 'Office XML',
}

const SOURCE_HINTS: Record<ParseSource, string> = {
  'native-text': 'PDF 原生文字层，可信度最高',
  ocr: 'OCR 模型识别结果',
  vlm: '视觉模型生成，无校准置信度',
  'office-xml': 'Office 原生 XML 解析',
}

const SOURCE_OVERLAY_CLASSES: Record<ParseSource, string> = {
  'native-text': 'border-success-500 bg-success-500/15',
  ocr: 'border-accent-400 bg-accent-400/15',
  vlm: 'border-warning-500 bg-warning-500/15',
  'office-xml': 'border-primary-400 bg-primary-400/15',
}

const SOURCE_BADGE_CLASSES: Record<ParseSource, string> = {
  'native-text': 'bg-success-500/10 text-success-500 border border-success-500/20',
  ocr: 'bg-accent-400/10 text-accent-400 border border-accent-400/20',
  vlm: 'bg-warning-500/10 text-warning-500 border border-warning-500/20',
  'office-xml': 'bg-primary-400/10 text-primary-400 border border-primary-400/20',
}

export function getBlockTypeLabel(type: string): string {
  return BLOCK_TYPE_LABELS[type as ParseBlockType] ?? type
}

export function getSourceLabel(source: string): string {
  return SOURCE_LABELS[source as ParseSource] ?? source
}

export function getSourceHint(source: string): string {
  return SOURCE_HINTS[source as ParseSource] ?? ''
}

export function getSourceOverlayClass(source: string): string {
  return SOURCE_OVERLAY_CLASSES[source as ParseSource] ?? 'border-border-default bg-bg-hover'
}

export function getSourceBadgeClass(source: string): string {
  return SOURCE_BADGE_CLASSES[source as ParseSource] ?? 'bg-bg-hover text-text-secondary border border-border-default'
}

// ============ 置信度 ============

/**
 * 置信度显示规则（#2/#8 契约）：
 * - vlm 一律显示“无置信度”，即使后端意外带上数字也不展示（禁止伪造）；
 * - 空值显示“未知”；
 * - 0-1 的模型 score 显示为百分比。
 */
export function formatConfidence(
  source: string,
  confidence: number | null | undefined,
): string {
  if (source === 'vlm') return '无置信度'
  if (confidence === null || confidence === undefined || Number.isNaN(confidence)) {
    return '未知'
  }
  const clamped = Math.min(1, Math.max(0, confidence))
  return `${(clamped * 100).toFixed(1)}%`
}

// ============ 块坐标 → 页面覆盖层 ============

export interface OverlayRect {
  left: number
  top: number
  width: number
  height: number
}

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value))
}

function round2(value: number): number {
  return Math.round(value * 100) / 100
}

/**
 * 把块 bbox（页面像素或 0-1000 归一化）换算为相对页面的百分比矩形。
 * 无效坐标（缺字段/非数字/零页尺寸/零面积）返回 null。
 */
export function bboxToOverlayRect(
  bbox: readonly number[] | null | undefined,
  page: { width?: number | null; height?: number | null },
): OverlayRect | null {
  if (!bbox || bbox.length < 4) return null
  const [x0, y0, x1, y1] = bbox
  if (![x0, y0, x1, y1].every((value) => Number.isFinite(value))) return null

  const pageWidth = Number(page?.width)
  const pageHeight = Number(page?.height)
  if (!Number.isFinite(pageWidth) || !Number.isFinite(pageHeight)) return null
  if (pageWidth <= 0 || pageHeight <= 0) return null

  const left = clampPercent((Math.min(x0, x1) / pageWidth) * 100)
  const top = clampPercent((Math.min(y0, y1) / pageHeight) * 100)
  const right = clampPercent((Math.max(x0, x1) / pageWidth) * 100)
  const bottom = clampPercent((Math.max(y0, y1) / pageHeight) * 100)
  const width = right - left
  const height = bottom - top

  if (width <= 0 || height <= 0) return null
  return {
    left: round2(left),
    top: round2(top),
    width: round2(width),
    height: round2(height),
  }
}

// ============ Job 状态 ============

export type JobPhase = 'idle' | 'running' | 'completed' | 'failed' | 'missing'

const STAGE_LABELS: Record<string, string> = {
  queued: '排队中',
  pending: '等待中',
  ocr: '解析中',
  llm: '抽取中',
  saving: '保存中',
  completed: '已完成',
  failed: '失败',
}

export function getJobPhase(
  job: Pick<ProcessingJob, 'status'> | null | undefined,
): JobPhase {
  if (!job) return 'missing'
  if (job.status === 'completed') return 'completed'
  if (job.status === 'failed') return 'failed'
  return 'running'
}

export function getJobStageLabel(stage?: string | null): string {
  if (!stage) return '未知'
  return STAGE_LABELS[stage] ?? stage
}

// ============ 预览来源类型 ============

export type DocumentPreviewKind = 'image' | 'pdf' | 'unsupported'

const IMAGE_EXTENSIONS = new Set([
  'png',
  'jpg',
  'jpeg',
  'gif',
  'bmp',
  'webp',
  'tif',
  'tiff',
])

export function resolveDocumentPreviewKind(
  doc:
    | { mime_type?: string | null; file_extension?: string | null; file_name?: string | null }
    | null
    | undefined,
): DocumentPreviewKind {
  if (!doc) return 'unsupported'

  const mime = (doc.mime_type || '').toLowerCase()
  if (mime.startsWith('image/')) return 'image'
  if (mime === 'application/pdf') return 'pdf'

  const extension = (
    doc.file_extension || doc.file_name?.split('.').pop() || ''
  )
    .toLowerCase()
    .replace(/^\./, '')
  if (IMAGE_EXTENSIONS.has(extension)) return 'image'
  if (extension === 'pdf') return 'pdf'
  return 'unsupported'
}

// ============ 轻量 markdown 解析 ============

export type MarkdownBlock =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'table'; header: string[]; rows: string[][] }
  | { kind: 'code'; text: string }
  | { kind: 'image'; alt: string }

const HEADING_RE = /^(#{1,6})\s+(.*)$/
const FENCE_RE = /^```/
const LIST_RE = /^\s*([-*+]|\d+[.)])\s+(.*)$/
const IMAGE_RE = /^!\[([^\]]*)\]\([^)]*\)\s*$/
const TABLE_SEPARATOR_RE = /^\s*\|?(\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$/

function splitTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function isTableStart(lines: string[], index: number): boolean {
  const line = lines[index]
  if (!line || !line.includes('|')) return false
  const next = lines[index + 1]
  return !!next && TABLE_SEPARATOR_RE.test(next)
}

export function parseMarkdown(markdown: string | null | undefined): MarkdownBlock[] {
  if (!markdown) return []
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const blocks: MarkdownBlock[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      index += 1
      continue
    }

    if (FENCE_RE.test(line.trim())) {
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !FENCE_RE.test(lines[index].trim())) {
        codeLines.push(lines[index])
        index += 1
      }
      blocks.push({ kind: 'code', text: codeLines.join('\n') })
      if (index < lines.length) index += 1
      continue
    }

    const heading = line.match(HEADING_RE)
    if (heading) {
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2].trim() })
      index += 1
      continue
    }

    const image = line.match(IMAGE_RE)
    if (image) {
      blocks.push({ kind: 'image', alt: image[1].trim() })
      index += 1
      continue
    }

    if (isTableStart(lines, index)) {
      const header = splitTableRow(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(splitTableRow(lines[index]))
        index += 1
      }
      blocks.push({ kind: 'table', header, rows })
      continue
    }

    const listItem = line.match(LIST_RE)
    if (listItem) {
      const ordered = /\d/.test(listItem[1])
      const items: string[] = []
      while (index < lines.length) {
        const matched = lines[index].match(LIST_RE)
        if (!matched) break
        items.push(matched[2].trim())
        index += 1
      }
      blocks.push({ kind: 'list', ordered, items })
      continue
    }

    const paragraphLines: string[] = []
    while (index < lines.length) {
      const current = lines[index]
      if (
        !current.trim() ||
        HEADING_RE.test(current) ||
        FENCE_RE.test(current.trim()) ||
        LIST_RE.test(current) ||
        IMAGE_RE.test(current) ||
        isTableStart(lines, index)
      ) {
        break
      }
      paragraphLines.push(current.trim())
      index += 1
    }
    blocks.push({ kind: 'paragraph', text: paragraphLines.join('\n') })
  }

  return blocks
}
