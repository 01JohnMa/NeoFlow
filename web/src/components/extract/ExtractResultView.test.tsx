import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ExtractResultView } from './ExtractResultView'
import type { ExtractResultView as View } from '@/types/extractSchema'

const view: View = { status: 'available', origin: 'execution_spec', target: 'per_doc', schema_hash: 'test', ui: {}, schema: {
  type: 'object', properties: {
    flag: { type: 'boolean' }, count: { type: 'number' }, missing: { type: 'string' },
    products: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, code: { type: 'string' },
    }, required: ['name'] } },
  },
} }

describe('pinned extraction result display', () => {
  it('preserves zero/false and never fills omitted keys in exported data', () => {
    const data = { flag: false, count: 0, products: [{ name: '记录' }] }
    const before = JSON.stringify(data)
    const html = renderToStaticMarkup(<ExtractResultView data={data} view={view} />)
    expect(html).toContain('false')
    expect(html).toContain('>0</pre>')
    expect(html).toContain('未返回')
    expect(html).toContain('不是准确率')
    expect(JSON.stringify(data)).toBe(before)
  })
  it('missing container does not invent an empty product row', () => {
    const html = renderToStaticMarkup(<ExtractResultView data={{}} view={view} />)
    expect(html).not.toContain('行</th>')
    expect(html).toContain('未返回')
  })
  it('missing view shows raw data without using any current configuration', () => {
    const html = renderToStaticMarkup(<ExtractResultView data={{ old: 0 }} />)
    expect(html).toContain('原始结果')
    expect(html).toContain('old')
  })
  it('keeps per-page outer instances separate from nested object lists', () => {
    const html = renderToStaticMarkup(<ExtractResultView data={[{ count: 0 }, { products: [] }]} view={{ ...view, target: 'per_page' }} />)
    expect(html).toContain('页面实例 1')
    expect(html).toContain('页面实例 2')
    expect(html).toContain('[]')
  })
})
