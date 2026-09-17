import type { ParseBlock, ParsePage, ParseResult } from '@/types'

/** 把受限 HTML（表格）转为纯文本，避免注入 Markdown 渲染。 */
export function htmlToText(html: string): string {
  if (typeof DOMParser === 'undefined') {
    return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
  }
  const doc = new DOMParser().parseFromString(html, 'text/html')
  return (doc.body.textContent || '').replace(/\s+/g, ' ').trim()
}

export function blockToText(block: ParseBlock): string {
  if (block.type === 'table' && block.table_html) return htmlToText(block.table_html)
  if (block.type === 'formula') return block.latex || block.text || ''
  if (block.type === 'figure') return block.text || '[图片]'
  return block.text || ''
}

export function pagePlainText(page: ParsePage): string {
  return [...page.blocks]
    .sort((a, b) => a.reading_order - b.reading_order)
    .map(blockToText)
    .filter((text) => text.trim().length > 0)
    .join('\n\n')
}

export function resultFullText(result: ParseResult): string {
  if (result.markdown && result.markdown.trim()) return result.markdown
  return result.pages
    .map(pagePlainText)
    .filter(Boolean)
    .join('\n\n---\n\n')
}
