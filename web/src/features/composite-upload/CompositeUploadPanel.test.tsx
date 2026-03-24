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
  it('将推送文件名输入放到统一侧栏并隐藏任务摘要与组内命名说明', () => {
    const html = renderToStaticMarkup(<CompositeUploadPanel scenario={scenario} />)

    expect(html).toContain('分组 1')
    expect(html).toContain('推送文件名')
    expect(html).not.toContain('任务摘要')
    expect(html).not.toContain('当前组自定义文件名')
    expect(html).not.toContain('实际生效名称')
  })
})
