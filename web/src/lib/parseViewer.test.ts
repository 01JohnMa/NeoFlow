import { describe, expect, it } from 'vitest'
import {
  bboxToOverlayRect,
  formatConfidence,
  getBlockTypeLabel,
  getJobPhase,
  getJobStageLabel,
  getSourceLabel,
  parseMarkdown,
  resolveDocumentPreviewKind,
} from '@/lib/parseViewer'

describe('bboxToOverlayRect', () => {
  it('把像素坐标换算为页面百分比', () => {
    expect(
      bboxToOverlayRect([100, 200, 300, 500], { width: 1000, height: 1000 }),
    ).toEqual({ left: 10, top: 20, width: 20, height: 30 })
  })

  it('支持 0-1000 归一化页面', () => {
    expect(
      bboxToOverlayRect([100, 50, 600, 500], { width: 1000, height: 1000 }),
    ).toEqual({ left: 10, top: 5, width: 50, height: 45 })
  })

  it('乱序坐标自动排序并裁剪到页面内', () => {
    expect(
      bboxToOverlayRect([1200, 500, -50, 200], { width: 1000, height: 1000 }),
    ).toEqual({ left: 0, top: 20, width: 100, height: 30 })
  })

  it('非法坐标返回 null', () => {
    expect(bboxToOverlayRect([1, 2, 3], { width: 100, height: 100 })).toBeNull()
    expect(
      bboxToOverlayRect([1, 2, 3, Number.NaN], { width: 100, height: 100 }),
    ).toBeNull()
    expect(bboxToOverlayRect([10, 10, 10, 50], { width: 100, height: 100 })).toBeNull()
    expect(bboxToOverlayRect([1, 2, 3, 4], { width: 0, height: 100 })).toBeNull()
    expect(bboxToOverlayRect(null, { width: 100, height: 100 })).toBeNull()
  })
})

describe('formatConfidence', () => {
  it('VLM 一律显示无置信度，即使后端带上数字', () => {
    expect(formatConfidence('vlm', null)).toBe('无置信度')
    expect(formatConfidence('vlm', undefined)).toBe('无置信度')
    expect(formatConfidence('vlm', 0.9)).toBe('无置信度')
  })

  it('空置信度显示未知', () => {
    expect(formatConfidence('ocr', null)).toBe('未知')
    expect(formatConfidence('ocr', undefined)).toBe('未知')
  })

  it('数字置信度显示百分比并收敛到 0-100%', () => {
    expect(formatConfidence('ocr', 0.923)).toBe('92.3%')
    expect(formatConfidence('native-text', 1)).toBe('100.0%')
    expect(formatConfidence('ocr', 1.5)).toBe('100.0%')
    expect(formatConfidence('ocr', -0.2)).toBe('0.0%')
  })
})

describe('labels', () => {
  it('映射块类型与来源，未知值原样返回', () => {
    expect(getBlockTypeLabel('title')).toBe('标题')
    expect(getBlockTypeLabel('unknown')).toBe('unknown')
    expect(getSourceLabel('native-text')).toBe('文字层')
    expect(getSourceLabel('office-xml')).toBe('Office XML')
  })
})

describe('job status', () => {
  it('区分任务阶段', () => {
    expect(getJobPhase(null)).toBe('missing')
    expect(getJobPhase({ status: 'queued' })).toBe('running')
    expect(getJobPhase({ status: 'processing' })).toBe('running')
    expect(getJobPhase({ status: 'completed' })).toBe('completed')
    expect(getJobPhase({ status: 'failed' })).toBe('failed')
  })

  it('阶段文案', () => {
    expect(getJobStageLabel('ocr')).toBe('解析中')
    expect(getJobStageLabel('saving')).toBe('保存中')
    expect(getJobStageLabel(null)).toBe('未知')
    expect(getJobStageLabel('custom')).toBe('custom')
  })
})

describe('resolveDocumentPreviewKind', () => {
  it('识别图片、PDF 与不支持的格式', () => {
    expect(resolveDocumentPreviewKind({ mime_type: 'image/png' })).toBe('image')
    expect(resolveDocumentPreviewKind({ mime_type: 'application/pdf' })).toBe('pdf')
    expect(resolveDocumentPreviewKind({ file_extension: 'pdf' })).toBe('pdf')
    expect(resolveDocumentPreviewKind({ file_name: '报告.JPG' })).toBe('image')
    expect(resolveDocumentPreviewKind({ file_name: 'a.docx' })).toBe('unsupported')
    expect(resolveDocumentPreviewKind(null)).toBe('unsupported')
  })
})

describe('parseMarkdown', () => {
  it('解析标题、段落、列表与代码块', () => {
    const blocks = parseMarkdown(
      '# 标题\n\n正文第一行\n正文第二行\n\n- 项目一\n- 项目二\n\n```\ncode\n```',
    )
    expect(blocks).toEqual([
      { kind: 'heading', level: 1, text: '标题' },
      { kind: 'paragraph', text: '正文第一行\n正文第二行' },
      { kind: 'list', ordered: false, items: ['项目一', '项目二'] },
      { kind: 'code', text: 'code' },
    ])
  })

  it('解析表格与有序列表', () => {
    const blocks = parseMarkdown(
      '| 名称 | 值 |\n| --- | --- |\n| A | 1 |\n\n1. 第一\n2. 第二',
    )
    expect(blocks[0]).toEqual({
      kind: 'table',
      header: ['名称', '值'],
      rows: [['A', '1']],
    })
    expect(blocks[1]).toEqual({ kind: 'list', ordered: true, items: ['第一', '第二'] })
  })

  it('解析独立图片行', () => {
    expect(parseMarkdown('![示意图](images/a.jpg)')).toEqual([
      { kind: 'image', alt: '示意图' },
    ])
  })

  it('空 markdown 返回空数组', () => {
    expect(parseMarkdown('')).toEqual([])
    expect(parseMarkdown(null)).toEqual([])
  })
})
