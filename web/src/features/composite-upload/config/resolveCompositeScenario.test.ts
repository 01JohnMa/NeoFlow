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

  it('有激活模板时启用单文件上传，并基于模板解析照明双文档场景', () => {
    const result = resolveUploadCapabilities({
      tenantCode: 'lighting',
      templates: [
        createTemplate({ id: 'sphere-tpl', code: 'integrating_sphere', name: '积分球模板' }),
        createTemplate({ id: 'distribution-tpl', code: 'light_distribution', name: '光分布模板' }),
        createTemplate({ id: 'other-tpl', code: 'other_template', name: '其他模板' }),
      ],
    })

    expect(result.uploadMode).toBe('single')
    expect(result.canUseSingleUpload).toBe(true)
    expect(result.singleTemplates.map(template => template.id)).toEqual([
      'sphere-tpl',
      'distribution-tpl',
      'other-tpl',
    ])
    expect(result.compositeScenarios).toHaveLength(1)
    expect(result.compositeScenarios[0]).toMatchObject({
      scenarioKey: 'lighting_pair',
      displayName: '照明分组上传',
      enabled: true,
      maxGroups: 5,
      slotDefinitions: [
        { slotKey: 'slotA', label: '积分球', templateId: 'sphere-tpl' },
        { slotKey: 'slotB', label: '光分布', templateId: 'distribution-tpl' },
      ],
    })
  })

  it('模板不全时场景仍可见，但只有已配置槽位可提交', () => {
    const result = resolveUploadCapabilities({
      tenantCode: 'lighting',
      templates: [createTemplate({ id: 'distribution-tpl', code: 'light_distribution', name: '光分布模板' })],
    })

    expect(result.compositeScenarios).toHaveLength(1)
    expect(result.compositeScenarios[0].enabled).toBe(true)
    expect(result.compositeScenarios[0].slotDefinitions).toEqual([
      {
        slotKey: 'slotB',
        label: '光分布',
        templateCode: 'light_distribution',
        templateId: 'distribution-tpl',
        required: false,
      },
    ])
  })
})
