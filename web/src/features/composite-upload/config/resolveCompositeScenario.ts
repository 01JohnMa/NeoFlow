import type { Template } from '@/store/useStore'
import type { CompositeScenarioConfig } from '@/features/composite-upload/core/types'

export interface UploadCapabilities {
  canUseCompositeUpload: boolean
  compositeScenarios: CompositeScenarioConfig[]
}

const GENERIC_BATCH_SCENARIO_KEY = 'generic_batch'
const GENERIC_BATCH_MAX_GROUPS = 10

function resolveGenericBatchScenario(templates: Template[], pairedMode: boolean): CompositeScenarioConfig | null {
  if (templates.length === 0) {
    return null
  }

  const slotDefinitions = pairedMode
    ? [
        { slotKey: 'slotA' as const, label: '文档 A', required: false },
        { slotKey: 'slotB' as const, label: '文档 B', required: false },
      ]
    : [
        { slotKey: 'slotA' as const, label: '文档', required: false },
      ]

  return {
    scenarioKey: GENERIC_BATCH_SCENARIO_KEY,
    displayName: '批量处理',
    description: pairedMode
      ? `按组上传文档并选择文档类型。单组支持双文件合并处理，最多 ${GENERIC_BATCH_MAX_GROUPS} 项任务。`
      : `按组上传文档并选择文档类型。单组支持多图片处理，最多 ${GENERIC_BATCH_MAX_GROUPS} 项任务。`,
    enabled: true,
    maxGroups: GENERIC_BATCH_MAX_GROUPS,
    slotDefinitions,
    templateOptions: templates.map(template => ({
      id: template.id,
      name: template.name,
      code: template.code,
    })),
    pushNameStrategy: 'slotA-first',
  }
}

export function resolveUploadCapabilities(params: {
  tenantCode: string | null | undefined
  templates: Template[]
  pairedBatchMode?: boolean
}): UploadCapabilities {
  const hasTenant = Boolean(params.tenantCode)
  const singleTemplates = hasTenant
    ? params.templates.filter(template => template.is_active !== false)
    : []

  const compositeScenarios = hasTenant
    ? [resolveGenericBatchScenario(singleTemplates, params.pairedBatchMode ?? false)].filter((scenario): scenario is CompositeScenarioConfig => Boolean(scenario))
    : []

  return {
    canUseCompositeUpload: compositeScenarios.length > 0,
    compositeScenarios,
  }
}
