import { blockToText } from '@/lib/parseContent'
import type { ParsePage } from '@/types'

/** 按页块确定性渲染（不用原始 HTML，不加载外部资源）。 */
export function PageContent({ page }: { page: ParsePage }) {
  const blocks = [...page.blocks].sort((a, b) => a.reading_order - b.reading_order)

  if (blocks.length === 0) {
    return <p className="text-sm text-text-muted">本页没有可展示的内容块</p>
  }

  return (
    <article className="space-y-3">
      {blocks.map((block) => {
        if (block.type === 'title') {
          return (
            <h3 key={block.id} className="text-lg font-semibold text-text-primary">
              {block.text}
            </h3>
          )
        }
        if (block.type === 'table') {
          return (
            <pre
              key={block.id}
              className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-bg-secondary p-3 text-xs text-text-secondary"
            >
              {blockToText(block)}
            </pre>
          )
        }
        if (block.type === 'formula') {
          return (
            <code key={block.id} className="block rounded bg-bg-secondary p-2 font-mono text-sm text-text-primary">
              {block.latex || block.text || ''}
            </code>
          )
        }
        if (block.type === 'figure') {
          return (
            <p key={block.id} className="text-sm text-text-muted">
              {block.text || '[图片]'}
            </p>
          )
        }
        return (
          <p key={block.id} className="whitespace-pre-wrap text-sm leading-relaxed text-text-secondary">
            {block.text}
          </p>
        )
      })}
    </article>
  )
}
