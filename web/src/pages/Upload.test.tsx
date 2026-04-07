import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Upload } from '@/pages/Upload'

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({
    tenantName: '测试部门',
    tenantCode: 'quality',
    templates: [],
    isLoading: false,
    pairedBatchMode: false,
  }),
}))

vi.mock('@/features/composite-upload/config/resolveCompositeScenario', () => ({
  resolveUploadCapabilities: () => ({
    canUseCompositeUpload: true,
    compositeScenarios: [
      {
        scenarioKey: 'generic_batch',
        displayName: '批量处理',
        description: '按组上传',
        enabled: true,
        maxGroups: 5,
        slotDefinitions: [{ slotKey: 'slotA', label: '文档', required: false }],
        templateOptions: [{ id: 'tpl-a', code: 'tpl_a', name: '模板A' }],
        pushNameStrategy: 'slotA-first',
      },
    ],
  }),
}))

vi.mock('@/features/composite-upload/CompositeUploadPanel', () => ({
  CompositeUploadPanel: () => <div>CompositeUploadPanel</div>,
}))

describe('Upload page', () => {
  it('统一到批处理入口，不再展示单文件上传入口', () => {
    const html = renderToStaticMarkup(<Upload />)

    expect(html).not.toContain('单文件上传')
    expect(html).not.toContain('SingleUploadPanel')
    expect(html).toContain('CompositeUploadPanel')
  })
})
