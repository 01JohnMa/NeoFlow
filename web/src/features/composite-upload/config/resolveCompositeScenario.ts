import type { Template } from '@/store/useStore'
import type { CompositeScenarioConfig } from '@/features/composite-upload/core/types'

export type UploadMode = 'single' | 'batch' | 'unknown'

export interface UploadCapabilities {
  uploadMode: UploadMode
  canUseSingleUpload: boolean
  canUseCompositeUpload: boolean
  singleTemplates: Template[]
  compositeScenarios: CompositeScenarioConfig[]
}

const GENERIC_BATCH_SCENARIO_KEY = 'generic_batch'
const GENERIC_BATCH_MAX_GROUPS = 5

function resolveGenericBatchScenario(templates: Template[]): CompositeScenarioConfig | null {
  if (templates.length === 0) {
    return null
  }

  return {
    scenarioKey: GENERIC_BATCH_SCENARIO_KEY,
    displayName: '批量处理',
    description: `按组上传文档并选择文档类型。单组支持单文件处理或双文件合并处理，最多 ${GENERIC_BATCH_MAX_GROUPS} 项任务。`,
    enabled: true,
    maxGroups: GENERIC_BATCH_MAX_GROUPS,
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
}): UploadCapabilities {
  const hasTenant = Boolean(params.tenantCode)
  const singleTemplates = hasTenant
    ? params.templates.filter(template => template.is_active !== false)
    : []

  const compositeScenarios = hasTenant
    ? [resolveGenericBatchScenario(singleTemplates)].filter((scenario): scenario is CompositeScenarioConfig => Boolean(scenario))
    : []

  return {
    uploadMode: hasTenant && singleTemplates.length > 0 ? 'single' : 'unknown',
    canUseSingleUpload: hasTenant && singleTemplates.length > 0,
    canUseCompositeUpload: compositeScenarios.length > 0,
    singleTemplates,
    compositeScenarios,
  }
}
