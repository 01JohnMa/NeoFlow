import { describe, expect, it } from 'vitest'
import type { Template } from '@/store/useStore'
import { resolveUploadCapabilities } from '@/features/composite-upload/config/resolveCompositeScenario'

function createTemplate(partial: Partial<Template>): Template {
  return {
    id: partial.id || 'tpl-id',
    name: partial.name || '模板',
    code: partial.code || 'template_code',
    required_doc_count: partial.required_doc_count || 1,
    is_active: partial.is_active ?? true,
    description: partial.description,
  }
}

describe('resolveUploadCapabilities', () => {
  it('无 tenantCode 时不暴露任何场景', () => {
    const result = resolveUploadCapabilities({
      tenantCode: null,
      templates: [createTemplate({ code: 'integrating_sphere' })],
    })

    expect(result.canUseCompositeUpload).toBe(false)
    expect(result.compositeScenarios).toEqual([])
  })

  it('默认单文件模式（pairedBatchMode 未传）：每组仅 1 个槽位', () => {
    const result = resolveUploadCapabilities({
      tenantCode: 'quality',
      templates: [
        createTemplate({ id: 'tpl-a', code: 'integrating_sphere', name: '积分球模板' }),
        createTemplate({ id: 'tpl-b', code: 'light_distribution', name: '光分布模板' }),
      ],
    })

    expect(result.canUseCompositeUpload).toBe(true)
    expect(result.compositeScenarios).toHaveLength(1)
    expect(result.compositeScenarios[0].slotDefinitions).toEqual([
      { slotKey: 'slotA', label: '文档', required: false },
    ])
  })

  it('pairedBatchMode=false：每组仅 1 个槽位（单文件模式）', () => {
    const result = resolveUploadCapabilities({
      tenantCode: 'quality',
      templates: [createTemplate({ id: 'tpl-only', code: 'quality_report', name: '质量报告模板' })],
      pairedBatchMode: false,
    })

    expect(result.compositeScenarios).toHaveLength(1)
    expect(result.compositeScenarios[0].slotDefinitions).toEqual([
      { slotKey: 'slotA', label: '文档', required: false },
    ])
    expect(result.compositeScenarios[0].templateOptions).toEqual([
      { id: 'tpl-only', name: '质量报告模板', code: 'quality_report' },
    ])
    expect(result.compositeScenarios[0].description).toContain('单组支持多图片处理')
  })

  it('pairedBatchMode=true：每组 2 个槽位（配对模式）', () => {
    const result = resolveUploadCapabilities({
      tenantCode: 'quality',
      templates: [
        createTemplate({ id: 'tpl-a', code: 'integrating_sphere', name: '积分球模板' }),
        createTemplate({ id: 'tpl-b', code: 'light_distribution', name: '光分布模板' }),
        createTemplate({ id: 'tpl-c', code: 'other_template', name: '其他模板' }),
      ],
      pairedBatchMode: true,
    })

    expect(result.canUseCompositeUpload).toBe(true)
    expect(result.compositeScenarios).toHaveLength(1)
    expect(result.compositeScenarios[0]).toMatchObject({
      scenarioKey: 'generic_batch',
      displayName: '批量处理',
      enabled: true,
      maxGroups: 10,
      slotDefinitions: [
        { slotKey: 'slotA', label: '文档 A' },
        { slotKey: 'slotB', label: '文档 B' },
      ],
      templateOptions: [
        { id: 'tpl-a', name: '积分球模板', code: 'integrating_sphere' },
        { id: 'tpl-b', name: '光分布模板', code: 'light_distribution' },
        { id: 'tpl-c', name: '其他模板', code: 'other_template' },
      ],
    })
  })

  it('只有一个模板时仍暴露通用批处理场景', () => {
    const result = resolveUploadCapabilities({
      tenantCode: 'quality',
      templates: [createTemplate({ id: 'tpl-only', code: 'quality_report', name: '质量报告模板' })],
      pairedBatchMode: true,
    })

    expect(result.compositeScenarios).toHaveLength(1)
    expect(result.compositeScenarios[0].slotDefinitions).toEqual([
      { slotKey: 'slotA', label: '文档 A', required: false },
      { slotKey: 'slotB', label: '文档 B', required: false },
    ])
    expect(result.compositeScenarios[0].templateOptions).toEqual([
      { id: 'tpl-only', name: '质量报告模板', code: 'quality_report' },
    ])
  })
})
