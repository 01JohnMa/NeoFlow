import type { BatchProcessItem } from '@/types'
import type {
  CompositeGroup,
  CompositeGroupStatusSummary,
  CompositeGroupValidationResult,
  CompositeScenarioConfig,
  CompositeSlotKey,
  CompositeUploadedFile,
} from './types'

const DEFAULT_MAX_GROUPS = 5

export interface BuiltCompositeBatchPayload {
  items: BatchProcessItem[]
  fileCustomPushNameMap: Record<string, string>
}

function stripExtension(filename: string): string {
  return filename.replace(/\.[^.]+$/, '')
}

function getConfiguredSlotKeys(scenario: CompositeScenarioConfig): CompositeSlotKey[] {
  return scenario.slotDefinitions.map(slot => slot.slotKey)
}

function getFilledSlotEntries(group: CompositeGroup, scenario: CompositeScenarioConfig): Array<[CompositeSlotKey, CompositeUploadedFile]> {
  return getConfiguredSlotKeys(scenario)
    .map(slotKey => [slotKey, group.documents[slotKey]] as const)
    .filter((entry): entry is [CompositeSlotKey, CompositeUploadedFile] => Boolean(entry[1]))
}

export function getUploadedFileIdentity(file: CompositeUploadedFile): string {
  return [file.file.name, file.file.size, file.file.lastModified, file.file.type].join('::')
}

export function createEmptyCompositeGroup(scenario: CompositeScenarioConfig): CompositeGroup {
  return {
    id: `composite-group-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    documents: Object.fromEntries(
      getConfiguredSlotKeys(scenario).map(slotKey => [slotKey, null])
    ),
  }
}

export function summarizeCompositeGroups(
  groups: CompositeGroup[],
  scenario: CompositeScenarioConfig,
): CompositeGroupStatusSummary {
  const slotCount = getConfiguredSlotKeys(scenario).length

  return groups.reduce<CompositeGroupStatusSummary>((summary, group) => {
    const filledCount = getFilledSlotEntries(group, scenario).length

    if (filledCount === 0) {
      summary.empty += 1
      return summary
    }

    if (filledCount === slotCount) {
      summary.complete += 1
    } else {
      summary.partial += 1
    }

    summary.totalTasks += 1
    return summary
  }, {
    empty: 0,
    complete: 0,
    partial: 0,
    totalTasks: 0,
  })
}

export function getDefaultCompositeGroupPushName(group: CompositeGroup, scenario: CompositeScenarioConfig): string {
  const slotOrder = scenario.pushNameStrategy === 'slotB-first'
    ? ['slotB', 'slotA']
    : scenario.pushNameStrategy === 'slotA-first'
      ? ['slotA', 'slotB']
      : getConfiguredSlotKeys(scenario)

  for (const slotKey of slotOrder) {
    const file = group.documents[slotKey]
    if (file) {
      return stripExtension(file.file.name)
    }
  }

  const firstAvailable = getFilledSlotEntries(group, scenario)[0]?.[1]
  return firstAvailable ? stripExtension(firstAvailable.file.name) : ''
}

export function isCompositeFileUsedInOtherGroups(groups: CompositeGroup[], currentGroupId: string, file: File): boolean {
  const identity = [file.name, file.size, file.lastModified, file.type].join('::')
  const currentGroup = groups.find(group => group.id === currentGroupId)
  const alreadyUsedInCurrentGroup = Boolean(currentGroup && Object.values(currentGroup.documents)
    .filter((item): item is CompositeUploadedFile => Boolean(item))
    .some(item => getUploadedFileIdentity(item) === identity))

  if (alreadyUsedInCurrentGroup) {
    return false
  }

  return groups.some(group => {
    if (group.id === currentGroupId) return false
    return Object.values(group.documents)
      .filter((item): item is CompositeUploadedFile => Boolean(item))
      .some(item => getUploadedFileIdentity(item) === identity)
  })
}

export function validateCompositeGroups(
  groups: CompositeGroup[],
  scenario: CompositeScenarioConfig,
): CompositeGroupValidationResult {
  const summary = summarizeCompositeGroups(groups, scenario)
  const groupErrors: Record<string, string[]> = {}
  const globalErrors: string[] = []
  const occupiedByIdentity = new Map<string, string[]>()
  const maxGroups = scenario.maxGroups || DEFAULT_MAX_GROUPS

  if (summary.totalTasks === 0) {
    globalErrors.push('请至少填写一个有效分组任务')
  }

  if (summary.totalTasks > maxGroups) {
    globalErrors.push(`任务项不能超过 ${maxGroups} 个（当前 ${summary.totalTasks} 个）`)
  }

  groups.forEach(group => {
    const errors: string[] = []
    const configuredSlotKeys = new Set(getConfiguredSlotKeys(scenario))

    Object.entries(group.documents).forEach(([slotKey, file]) => {
      if (!file) return

      if (!configuredSlotKeys.has(slotKey)) {
        errors.push(`缺少“${slotKey}”对应模板，当前分组无法提交该槽位文件`)
      }

      const identity = getUploadedFileIdentity(file)
      occupiedByIdentity.set(identity, [...(occupiedByIdentity.get(identity) || []), group.id])
    })

    scenario.slotDefinitions.forEach(slotDefinition => {
      const file = group.documents[slotDefinition.slotKey]
      if (!file) return

      if (!slotDefinition.templateId) {
        errors.push(`缺少“${slotDefinition.slotKey}”对应模板，当前分组无法提交该槽位文件`)
      }
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
    const filledCount = getFilledSlotEntries(group, scenario).length
    if (filledCount === 0 || groupErrors[group.id]?.length) {
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

export function getSubmittableCompositeGroups(groups: CompositeGroup[], scenario: CompositeScenarioConfig): CompositeGroup[] {
  const validation = validateCompositeGroups(groups, scenario)

  if (validation.globalErrors.length > 0) {
    return []
  }

  return groups.filter(group => getFilledSlotEntries(group, scenario).length > 0 && !validation.groupErrors[group.id]?.length)
}

export function getSubmittableCompositeUploadFiles(
  groups: CompositeGroup[],
  scenario: CompositeScenarioConfig,
): CompositeUploadedFile[] {
  const fileMap = new Map<string, CompositeUploadedFile>()

  getSubmittableCompositeGroups(groups, scenario).forEach(group => {
    getFilledSlotEntries(group, scenario).forEach(([, file]) => {
      fileMap.set(getUploadedFileIdentity(file), file)
    })
  })

  return Array.from(fileMap.values())
}

export function buildCompositeBatchPayload(params: {
  groups: CompositeGroup[]
  scenario: CompositeScenarioConfig
  uploadResults: Record<string, { document_id: string; file_path: string }>
  groupCustomPushNames: Record<string, string>
}): BuiltCompositeBatchPayload {
  const items: BatchProcessItem[] = []
  const fileCustomPushNameMap: Record<string, string> = {}

  const getDocumentId = (file: CompositeUploadedFile | null) => {
    if (!file) return undefined
    return params.uploadResults[file.id]?.document_id || file.documentId
  }

  getSubmittableCompositeGroups(params.groups, params.scenario).forEach(group => {
    const filledEntries = getFilledSlotEntries(group, params.scenario)
    const customPushName = (params.groupCustomPushNames[group.id] || '').trim() || getDefaultCompositeGroupPushName(group, params.scenario)

    if (customPushName) {
      filledEntries.forEach(([, file]) => {
        fileCustomPushNameMap[file.id] = customPushName
      })
    }

    if (filledEntries.length >= 2) {
      const [primarySlotKey, primaryFile] = filledEntries[0]
      const [pairedSlotKey, pairedFile] = filledEntries[1]
      const primaryTemplate = params.scenario.slotDefinitions.find(slot => slot.slotKey === primarySlotKey)
      const pairedTemplate = params.scenario.slotDefinitions.find(slot => slot.slotKey === pairedSlotKey)
      const primaryDocumentId = getDocumentId(primaryFile)
      const pairedDocumentId = getDocumentId(pairedFile)

      if (primaryDocumentId && pairedDocumentId && primaryTemplate?.templateId && pairedTemplate?.templateId) {
        items.push({
          document_id: primaryDocumentId,
          template_id: primaryTemplate.templateId,
          paired_document_id: pairedDocumentId,
          paired_template_id: pairedTemplate.templateId,
          custom_push_name: customPushName || undefined,
        })
      }

      return
    }

    if (filledEntries.length === 1) {
      const [slotKey, file] = filledEntries[0]
      const template = params.scenario.slotDefinitions.find(slot => slot.slotKey === slotKey)
      const documentId = getDocumentId(file)

      if (documentId && template?.templateId) {
        items.push({
          document_id: documentId,
          template_id: template.templateId,
          custom_push_name: customPushName || undefined,
        })
      }
    }
  })

  return { items, fileCustomPushNameMap }
}
