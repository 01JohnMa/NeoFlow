import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { CompositeUploadPanel } from '@/features/composite-upload/CompositeUploadPanel'
import type { CompositeScenarioConfig } from '@/features/composite-upload/core/types'

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/services/documents', () => ({
  default: {
    upload: vi.fn(),
    submitBatchProcess: vi.fn(),
    getBatchJobStatus: vi.fn(),
  },
}))

const scenario: CompositeScenarioConfig = {
  scenarioKey: 'generic_batch',
  displayName: '批量处理',
  description: '按组上传文档',
  enabled: true,
  maxGroups: 5,
  slotDefinitions: [
    {
      slotKey: 'slotA',
      label: '文档 A',
      required: false,
    },
    {
      slotKey: 'slotB',
      label: '文档 B',
      required: false,
    },
  ],
  templateOptions: [
    { id: 'tpl-a', name: '模板 A', code: 'template_a' },
    { id: 'tpl-b', name: '模板 B', code: 'template_b' },
  ],
  pushNameStrategy: 'slotB-first',
}

describe('CompositeUploadPanel', () => {
  it('将文档槽位标题合并进类型选择文案以减少纵向信息', () => {
    const html = renderToStaticMarkup(<CompositeUploadPanel scenario={scenario} />)

    expect(html).toContain('aria-label="推送文件名"')
    expect(html).toContain('推送名')
    expect(html).toContain('aria-label="删除当前分组"')
    expect(html).toContain('text-error-400')
    expect(html).toContain('选择A文档类型...')
    expect(html).toContain('选择B文档类型...')
    expect(html).not.toContain('>文档 A<')
    expect(html).not.toContain('>文档 B<')
    expect(html).not.toContain('>分组 1<')
    expect(html).not.toContain('>空组<')
    expect(html).not.toContain('>完整组<')
    expect(html).not.toContain('>部分组<')
    expect(html).not.toContain('>推送文件名<')
    expect(html).not.toContain('推送文件名侧栏')
    expect(html).not.toContain('名称#1')
    expect(html).not.toContain('按组上传文档')
    expect(html).not.toContain('按分组命名')
    expect(html).not.toContain('请先在该组上传文件')
    expect(html).not.toContain('使用推荐名')
    expect(html).not.toContain('任务摘要')
    expect(html).not.toContain('当前组自定义文件名')
    expect(html).not.toContain('实际生效名称')
  })

  it('单槽位批处理场景启用多选文件输入', () => {
    const singleSlotScenario: CompositeScenarioConfig = {
      ...scenario,
      slotDefinitions: [
        {
          slotKey: 'slotA',
          label: '文档',
          required: false,
        },
      ],
    }
    const html = renderToStaticMarkup(<CompositeUploadPanel scenario={singleSlotScenario} />)

    expect(html).toContain('type="file"')
    expect(html).toContain('multiple=""')
  })
})
