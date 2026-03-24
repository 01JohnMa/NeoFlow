import type { Template } from '@/store/useStore'
import type { CompositeScenarioConfig } from '@/features/composite-upload/core/types'

export const INTEGRATING_SPHERE_TEMPLATE_CODE = 'integrating_sphere'
export const LIGHT_DISTRIBUTION_TEMPLATE_CODE = 'light_distribution'
export const LIGHTING_SCENARIO_KEY = 'lighting_pair'
export const LIGHTING_MAX_GROUPS = 5

export function resolveLightingScenario(templates: Template[]): CompositeScenarioConfig | null {
  const integratingSphereTemplate =
    templates.find(template => template.code === INTEGRATING_SPHERE_TEMPLATE_CODE && template.is_active !== false) || null
  const lightDistributionTemplate =
    templates.find(template => template.code === LIGHT_DISTRIBUTION_TEMPLATE_CODE && template.is_active !== false) || null

  if (!integratingSphereTemplate && !lightDistributionTemplate) {
    return null
  }

  const slotDefinitions = [
    integratingSphereTemplate
      ? {
          slotKey: 'slotA',
          label: '积分球',
          templateCode: INTEGRATING_SPHERE_TEMPLATE_CODE,
          templateId: integratingSphereTemplate.id,
          required: false,
        }
      : null,
    lightDistributionTemplate
      ? {
          slotKey: 'slotB',
          label: '光分布',
          templateCode: LIGHT_DISTRIBUTION_TEMPLATE_CODE,
          templateId: lightDistributionTemplate.id,
          required: false,
        }
      : null,
  ].filter((item): item is NonNullable<typeof item> => Boolean(item))

  return {
    scenarioKey: LIGHTING_SCENARIO_KEY,
    displayName: '照明分组上传',
    description: `按组填写积分球与光分布文件。支持完整双文件组，也支持仅上传单侧文件。最多 ${LIGHTING_MAX_GROUPS} 项任务。`,
    enabled: true,
    maxGroups: LIGHTING_MAX_GROUPS,
    slotDefinitions,
    pushNameStrategy: 'slotB-first',
  }
}
