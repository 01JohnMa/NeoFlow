import type { Template } from '@/store/useStore'
import type { CompositeScenarioConfig } from '@/features/composite-upload/core/types'
import { resolveLightingScenario } from '@/features/composite-upload/scenarios/lighting/adapter'

export type UploadMode = 'single' | 'batch' | 'unknown'

export interface UploadCapabilities {
  uploadMode: UploadMode
  canUseSingleUpload: boolean
  canUseCompositeUpload: boolean
  singleTemplates: Template[]
  compositeScenarios: CompositeScenarioConfig[]
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
    ? [resolveLightingScenario(singleTemplates)].filter((scenario): scenario is CompositeScenarioConfig => Boolean(scenario))
    : []

  return {
    uploadMode: hasTenant && singleTemplates.length > 0 ? 'single' : 'unknown',
    canUseSingleUpload: hasTenant && singleTemplates.length > 0,
    canUseCompositeUpload: compositeScenarios.length > 0,
    singleTemplates,
    compositeScenarios,
  }
}
