import { describe, expect, it } from 'vitest'
import { blockToText, htmlToText, pagePlainText, resultFullText } from './parseContent'
import type { ParseBlock, ParsePage, ParseResult } from '@/types'

function makeBlock(overrides: Partial<ParseBlock> = {}): ParseBlock {
  return {
    id: 'b1',
    type: 'text',
    bbox: [],
    text: null,
    table_html: null,
    image_path: null,
    latex: null,
    source: 'native-text',
    confidence: null,
    reading_order: 1,
    ...overrides,
  }
}

function makePage(overrides: Partial<ParsePage> = {}): ParsePage {
  return {
    page_no: 1,
    width: 100,
    height: 200,
    coordinate_space: 'pixel',
    markdown: null,
    blocks: [],
    ...overrides,
  }
}

describe('parseContent', () => {
  it('htmlToText 剥离标签且不保留 HTML', () => {
    const text = htmlToText('<table><tr><td>甲</td><td>乙</td></tr></table>')
    expect(text).toContain('甲')
    expect(text).not.toContain('<')
  })

  it('blockToText 覆盖表格/公式/图片', () => {
    expect(blockToText(makeBlock({ type: 'table', table_html: '<td>x</td>' }))).toBe('x')
    expect(blockToText(makeBlock({ type: 'formula', latex: 'E=mc^2' }))).toBe('E=mc^2')
    expect(blockToText(makeBlock({ type: 'figure', text: null }))).toBe('[图片]')
  })

  it('pagePlainText 按阅读顺序拼接并过滤空块', () => {
    const page = makePage({
      blocks: [
        makeBlock({ id: 'b2', reading_order: 2, text: '第二段' }),
        makeBlock({ id: 'b1', reading_order: 1, text: '第一段' }),
        makeBlock({ id: 'b3', reading_order: 3, text: '   ' }),
      ],
    })
    expect(pagePlainText(page)).toBe('第一段\n\n第二段')
  })

  it('resultFullText 优先使用 full markdown，缺失时按页拼接', () => {
    const full = { pages: [], markdown: '# 全文', engine: {}, warnings: [] } as ParseResult
    expect(resultFullText(full)).toBe('# 全文')

    const perPage = {
      pages: [
        makePage({ page_no: 1, blocks: [makeBlock({ text: '一' })] }),
        makePage({ page_no: 2, blocks: [makeBlock({ text: '二' })] }),
      ],
      markdown: '',
      engine: {},
      warnings: [],
    } as ParseResult
    expect(resultFullText(perPage)).toBe('一\n\n---\n\n二')
  })
})
