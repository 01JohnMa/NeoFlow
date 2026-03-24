import { describe, expect, it } from 'vitest'
import type { Template } from '@/store/useStore'
import { resolveLightingScenario } from '@/features/composite-upload/scenarios/lighting/adapter'

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

describe('resolveLightingScenario', () => {
  it('将照明模板解析为通用双文档场景配置', () => {
    const scenario = resolveLightingScenario([
      createTemplate({ id: 'sphere-tpl', code: 'integrating_sphere', name: '积分球模板' }),
      createTemplate({ id: 'distribution-tpl', code: 'light_distribution', name: '光分布模板' }),
    ])

    expect(scenario).toMatchObject({
      scenarioKey: 'lighting_pair',
      displayName: '照明分组上传',
      enabled: true,
      pushNameStrategy: 'slotB-first',
      slotDefinitions: [
        { slotKey: 'slotA', label: '积分球', templateId: 'sphere-tpl' },
        { slotKey: 'slotB', label: '光分布', templateId: 'distribution-tpl' },
      ],
    })
  })

  it('模板全缺失时不返回场景', () => {
    expect(resolveLightingScenario([])).toBeNull()
  })
})
