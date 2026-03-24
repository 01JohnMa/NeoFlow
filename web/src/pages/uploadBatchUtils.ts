import type { BatchProcessItem } from '@/types'
import type { Template } from '@/store/useStore'
import type { LightingGroup, UploadedFile, SlotKey } from '@/components/BatchMergePairing'

export const INTEGRATING_SPHERE_TEMPLATE_CODE = 'integrating_sphere'
export const LIGHT_DISTRIBUTION_TEMPLATE_CODE = 'light_distribution'
export const MAX_BATCH_TASKS = 5

export interface FixedLightingTemplates {
  integratingSphereTemplate: Template | null
  lightDistributionTemplate: Template | null
  lightingTemplatesReady: boolean
}

export interface GroupStatusSummary {
  empty: number
  complete: number
  sphereOnly: number
  distributionOnly: number
  totalTasks: number
}

export interface GroupValidationResult {
  canSubmit: boolean
  groupErrors: Record<string, string[]>
  globalErrors: string[]
  validTaskCount: number
}

export interface BuiltBatchPayload {
  items: BatchProcessItem[]
  fileCustomPushNameMap: Record<string, string>
}

function stripExtension(filename: string): string {
  return filename.replace(/\.[^.]+$/, '')
}

export function resolveEffectivePushName(customName: string, fallbackName: string): string {
  return customName.trim() || fallbackName.trim()
}

export function getDefaultSinglePushName(file: File | null, _template: Template | null = null): string {
  if (!file) return ''
  return stripExtension(file.name)
}

function getLightingFileIdentity(file: File): string {
  return [file.name, file.size, file.lastModified, file.type].join('::')
}

function getUploadedFileIdentity(file: UploadedFile): string {
  return getLightingFileIdentity(file.file)
}

export function resolveFixedLightingTemplates(templates: Template[]): FixedLightingTemplates {
  const integratingSphereTemplate =
    templates.find(t => t.code === INTEGRATING_SPHERE_TEMPLATE_CODE && t.is_active !== false) || null
  const lightDistributionTemplate =
    templates.find(t => t.code === LIGHT_DISTRIBUTION_TEMPLATE_CODE && t.is_active !== false) || null

  return {
    integratingSphereTemplate,
    lightDistributionTemplate,
    lightingTemplatesReady: Boolean(integratingSphereTemplate || lightDistributionTemplate),
  }
}

export function createEmptyLightingGroup(): LightingGroup {
  return {
    id: `lighting-group-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    sphereFile: null,
    distributionFile: null,
  }
}

export function getLightingGroupStatus(group: LightingGroup): 'empty' | 'complete' | 'sphere-only' | 'distribution-only' {
  if (group.sphereFile && group.distributionFile) return 'complete'
  if (group.sphereFile) return 'sphere-only'
  if (group.distributionFile) return 'distribution-only'
  return 'empty'
}

export function summarizeLightingGroups(groups: LightingGroup[]): GroupStatusSummary {
  return groups.reduce<GroupStatusSummary>((summary, group) => {
    const status = getLightingGroupStatus(group)

    if (status === 'empty') {
      summary.empty += 1
      return summary
    }

    if (status === 'complete') {
      summary.complete += 1
    } else if (status === 'sphere-only') {
      summary.sphereOnly += 1
    } else {
      summary.distributionOnly += 1
    }

    summary.totalTasks += 1
    return summary
  }, {
    empty: 0,
    complete: 0,
    sphereOnly: 0,
    distributionOnly: 0,
    totalTasks: 0,
  })
}

export function getDefaultGroupPushName(group: LightingGroup): string {
  const distributionName = group.distributionFile ? stripExtension(group.distributionFile.file.name) : ''
  const sphereName = group.sphereFile ? stripExtension(group.sphereFile.file.name) : ''

  return distributionName || sphereName || ''
}

export function isLightingFileUsedInOtherGroups(
  groups: LightingGroup[],
  currentGroupId: string,
  _slotKey: SlotKey,
  file: File
): boolean {
  const identity = getLightingFileIdentity(file)

  return groups.some(group => {
    if (group.id === currentGroupId) return false
    return [group.sphereFile, group.distributionFile]
      .filter((item): item is UploadedFile => Boolean(item))
      .some(item => getUploadedFileIdentity(item) === identity)
  })
}

function collectGroupFiles(group: LightingGroup): UploadedFile[] {
  return [group.sphereFile, group.distributionFile].filter((item): item is UploadedFile => Boolean(item))
}

export function getSubmittableUploadFiles(
  groups: LightingGroup[],
  fixedTemplates: FixedLightingTemplates
): UploadedFile[] {
  const fileMap = new Map<string, UploadedFile>()

  getSubmittableLightingGroups(groups, fixedTemplates).forEach(group => {
    collectGroupFiles(group).forEach(file => {
      fileMap.set(getUploadedFileIdentity(file), file)
    })
  })

  return Array.from(fileMap.values())
}

export function validateLightingGroups(
  groups: LightingGroup[],
  fixedTemplates: FixedLightingTemplates
): GroupValidationResult {
  const summary = summarizeLightingGroups(groups)
  const groupErrors: Record<string, string[]> = {}
  const globalErrors: string[] = []
  const occupiedByIdentity = new Map<string, string[]>()

  if (summary.totalTasks === 0) {
    globalErrors.push('请至少填写一个有效分组任务')
  }

  if (summary.totalTasks > MAX_BATCH_TASKS) {
    globalErrors.push(`任务项不能超过 ${MAX_BATCH_TASKS} 个（当前 ${summary.totalTasks} 个）`)
  }

  groups.forEach(group => {
    const errors: string[] = []
    const status = getLightingGroupStatus(group)

    if ((status === 'complete' || status === 'sphere-only') && !fixedTemplates.integratingSphereTemplate) {
      errors.push('缺少“积分球”固定模板，当前分组无法提交积分球文件')
    }

    if ((status === 'complete' || status === 'distribution-only') && !fixedTemplates.lightDistributionTemplate) {
      errors.push('缺少“光分布”固定模板，当前分组无法提交光分布文件')
    }

    collectGroupFiles(group).forEach(file => {
      const identity = getUploadedFileIdentity(file)
      occupiedByIdentity.set(identity, [...(occupiedByIdentity.get(identity) || []), group.id])
    })

    if (errors.length > 0) {
      groupErrors[group.id] = errors
    }
  })

  let hasDuplicateUsage = false
  occupiedByIdentity.forEach(groupIds => {
    if (groupIds.length <= 1) return
    hasDuplicateUsage = true
    groupIds.forEach(groupId => {
      groupErrors[groupId] = [
        ...(groupErrors[groupId] || []),
        '文件已被重复占用，请在其他分组中移除后再提交',
      ]
    })
  })

  if (hasDuplicateUsage) {
    globalErrors.push('存在重复占用文件的分组，请先调整后再提交')
  }

  const validTaskCount = groups.reduce((count, group) => {
    const status = getLightingGroupStatus(group)
    if (status === 'empty' || groupErrors[group.id]?.length) {
      return count
    }
    return count + 1
  }, 0)

  return {
    canSubmit: globalErrors.length === 0 && validTaskCount > 0,
    groupErrors,
    globalErrors,
    validTaskCount,
  }
}

export function getSubmittableLightingGroups(
  groups: LightingGroup[],
  fixedTemplates: FixedLightingTemplates
): LightingGroup[] {
  const validation = validateLightingGroups(groups, fixedTemplates)

  if (validation.globalErrors.length > 0) {
    return []
  }

  return groups.filter(group => {
    const status = getLightingGroupStatus(group)
    return status !== 'empty' && !validation.groupErrors[group.id]?.length
  })
}

export function buildLightingBatchPayload(params: {
  groups: LightingGroup[]
  fixedTemplates: FixedLightingTemplates
  uploadResults: Record<string, { document_id: string; file_path: string }>
  batchCustomPushNames: Record<string, string>
}): BuiltBatchPayload {
  const items: BatchProcessItem[] = []
  const fileCustomPushNameMap: Record<string, string> = {}

  const getDocumentId = (file: UploadedFile | null) => {
    if (!file) return undefined
    return params.uploadResults[file.id]?.document_id || file.documentId
  }

  const submittableGroups = getSubmittableLightingGroups(params.groups, params.fixedTemplates)

  submittableGroups.forEach(group => {
    const status = getLightingGroupStatus(group)
    const customPushName = resolveEffectivePushName(
      params.batchCustomPushNames[group.id] || '',
      getDefaultGroupPushName(group)
    )

    if (customPushName) {
      if (group.sphereFile) fileCustomPushNameMap[group.sphereFile.id] = customPushName
      if (group.distributionFile) fileCustomPushNameMap[group.distributionFile.id] = customPushName
    }

    if (
      status === 'complete'
      && params.fixedTemplates.integratingSphereTemplate
      && params.fixedTemplates.lightDistributionTemplate
    ) {
      const sphereDocumentId = getDocumentId(group.sphereFile)
      const distributionDocumentId = getDocumentId(group.distributionFile)

      if (sphereDocumentId && distributionDocumentId) {
        items.push({
          document_id: sphereDocumentId,
          template_id: params.fixedTemplates.integratingSphereTemplate.id,
          paired_document_id: distributionDocumentId,
          paired_template_id: params.fixedTemplates.lightDistributionTemplate.id,
          custom_push_name: customPushName || undefined,
        })
      }

      return
    }

    if (status === 'sphere-only' && params.fixedTemplates.integratingSphereTemplate) {
      const sphereDocumentId = getDocumentId(group.sphereFile)
      if (sphereDocumentId) {
        items.push({
          document_id: sphereDocumentId,
          template_id: params.fixedTemplates.integratingSphereTemplate.id,
          custom_push_name: customPushName || undefined,
        })
      }
      return
    }

    if (status === 'distribution-only' && params.fixedTemplates.lightDistributionTemplate) {
      const distributionDocumentId = getDocumentId(group.distributionFile)
      if (distributionDocumentId) {
        items.push({
          document_id: distributionDocumentId,
          template_id: params.fixedTemplates.lightDistributionTemplate.id,
          custom_push_name: customPushName || undefined,
        })
      }
    }
  })

  return { items, fileCustomPushNameMap }
}
