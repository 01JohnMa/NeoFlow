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
  it('无 tenantCode 时返回 unknown 且不暴露任何场景', () => {
    const result = resolveUploadCapabilities({
      tenantCode: null,
      templates: [createTemplate({ code: 'integrating_sphere' })],
    })

    expect(result.uploadMode).toBe('unknown')
    expect(result.canUseSingleUpload).toBe(false)
    expect(result.compositeScenarios).toEqual([])
  })

  it('有激活模板时启用单文件上传，并暴露通用批处理场景', () => {
    const result = resolveUploadCapabilities({
      tenantCode: 'quality',
      templates: [
        createTemplate({ id: 'tpl-a', code: 'integrating_sphere', name: '积分球模板' }),
        createTemplate({ id: 'tpl-b', code: 'light_distribution', name: '光分布模板' }),
        createTemplate({ id: 'tpl-c', code: 'other_template', name: '其他模板' }),
      ],
    })

    expect(result.uploadMode).toBe('single')
    expect(result.canUseSingleUpload).toBe(true)
    expect(result.canUseCompositeUpload).toBe(true)
    expect(result.singleTemplates.map(template => template.id)).toEqual([
      'tpl-a',
      'tpl-b',
      'tpl-c',
    ])
    expect(result.compositeScenarios).toHaveLength(1)
    expect(result.compositeScenarios[0]).toMatchObject({
      scenarioKey: 'generic_batch',
      displayName: '批量处理',
      enabled: true,
      maxGroups: 5,
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

  it('只有一个模板时仍暴露通用批处理场景，供用户做单文件批处理', () => {
    const result = resolveUploadCapabilities({
      tenantCode: 'quality',
      templates: [createTemplate({ id: 'tpl-only', code: 'quality_report', name: '质量报告模板' })],
    })

    expect(result.compositeScenarios).toHaveLength(1)
    expect(result.compositeScenarios[0].slotDefinitions).toEqual([
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
    ])
    expect(result.compositeScenarios[0].templateOptions).toEqual([
      {
        id: 'tpl-only',
        name: '质量报告模板',
        code: 'quality_report',
      },
    ])
  })
})
