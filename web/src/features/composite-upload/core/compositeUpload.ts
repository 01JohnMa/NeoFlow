import type { BatchProcessItem } from '@/types'
import type {
  CompositeGroup,
  CompositeGroupStatusSummary,
  CompositeGroupValidationResult,
  CompositeScenarioConfig,
  CompositeScenarioSlotDefinition,
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

function getFilledSlotEntries(group: CompositeGroup, scenario: CompositeScenarioConfig): Array<[CompositeSlotKey, CompositeUploadedFile[]]> {
  return getConfiguredSlotKeys(scenario)
    .map(slotKey => [slotKey, group.documents[slotKey]] as const)
    .filter((entry): entry is [CompositeSlotKey, CompositeUploadedFile[]] => entry[1].length > 0)
}

function getAllFilledFiles(group: CompositeGroup, scenario: CompositeScenarioConfig): CompositeUploadedFile[] {
  return getFilledSlotEntries(group, scenario).flatMap(([, files]) => files)
}

function getSlotDefinition(
  scenario: CompositeScenarioConfig,
  slotKey: CompositeSlotKey,
): CompositeScenarioSlotDefinition | undefined {
  return scenario.slotDefinitions.find(slot => slot.slotKey === slotKey)
}

function getEffectiveTemplateId(
  group: CompositeGroup,
  scenario: CompositeScenarioConfig,
  slotKey: CompositeSlotKey,
): string | null {
  const selectedTemplateId = group.templateSelections[slotKey]
  if (selectedTemplateId) {
    return selectedTemplateId
  }

  return getSlotDefinition(scenario, slotKey)?.templateId || null
}

function isAvailableTemplateSelection(scenario: CompositeScenarioConfig, templateId: string): boolean {
  if (scenario.templateOptions.length === 0) {
    return true
  }

  return scenario.templateOptions.some(option => option.id === templateId)
}

export function getUploadedFileIdentity(file: CompositeUploadedFile): string {
  return [file.file.name, file.file.size, file.file.lastModified, file.file.type].join('::')
}

export function createEmptyCompositeGroup(scenario: CompositeScenarioConfig): CompositeGroup {
  const configuredSlotKeys = getConfiguredSlotKeys(scenario)

  return {
    id: `composite-group-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    documents: Object.fromEntries(
      configuredSlotKeys.map(slotKey => [slotKey, []]),
    ),
    templateSelections: Object.fromEntries(
      configuredSlotKeys.map(slotKey => [slotKey, null]),
    ),
  }
}

/** 新增分组时复用第一组在各槽位已选的文档类型（未出现的槽位保持空分组默认 null） */
export function createEmptyCompositeGroupSeededFromFirst(
  scenario: CompositeScenarioConfig,
  firstGroup: CompositeGroup,
): CompositeGroup {
  const base = createEmptyCompositeGroup(scenario)
  const keys = getConfiguredSlotKeys(scenario)

  return {
    ...base,
    templateSelections: Object.fromEntries(
      keys.map((slotKey) => {
        const fromFirst = firstGroup.templateSelections[slotKey]
        return [slotKey, fromFirst !== undefined ? fromFirst : base.templateSelections[slotKey]]
      }),
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
    const filledTaskCount = getAllFilledFiles(group, scenario).length

    if (filledCount === 0) {
      summary.empty += 1
      return summary
    }

    if (filledCount === slotCount) {
      summary.complete += 1
    } else {
      summary.partial += 1
    }

    summary.totalTasks += filledTaskCount
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
    const file = group.documents[slotKey]?.[0]
    if (file) {
      return stripExtension(file.file.name)
    }
  }

  const firstAvailable = getAllFilledFiles(group, scenario)[0]
  return firstAvailable ? stripExtension(firstAvailable.file.name) : ''
}

export function isCompositeFileUsedInOtherGroups(groups: CompositeGroup[], currentGroupId: string, file: File): boolean {
  const identity = [file.name, file.size, file.lastModified, file.type].join('::')
  const currentGroup = groups.find(group => group.id === currentGroupId)
  const alreadyUsedInCurrentGroup = Boolean(currentGroup && Object.values(currentGroup.documents)
    .flatMap(slotFiles => slotFiles)
    .some(item => getUploadedFileIdentity(item) === identity))

  if (alreadyUsedInCurrentGroup) {
    return false
  }

  return groups.some(group => {
    if (group.id === currentGroupId) return false
    return Object.values(group.documents)
      .flatMap(slotFiles => slotFiles)
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

    Object.entries(group.documents).forEach(([slotKey, slotFiles]) => {
      if (slotFiles.length === 0) return

      if (!configuredSlotKeys.has(slotKey)) {
        errors.push(`缺少“${slotKey}”对应模板，当前分组无法提交该槽位文件`)
      }

      slotFiles.forEach((file) => {
        const identity = getUploadedFileIdentity(file)
        occupiedByIdentity.set(identity, [...(occupiedByIdentity.get(identity) || []), group.id])
      })
    })

    scenario.slotDefinitions.forEach(slotDefinition => {
      const slotFiles = group.documents[slotDefinition.slotKey]
      if (slotFiles.length === 0) return

      const effectiveTemplateId = getEffectiveTemplateId(group, scenario, slotDefinition.slotKey)
      if (!effectiveTemplateId) {
        errors.push(`请为“${slotDefinition.label}”选择文档类型后再提交`)
        return
      }

      if (!isAvailableTemplateSelection(scenario, effectiveTemplateId)) {
        errors.push(`“${slotDefinition.label}”选择的文档类型已不可用，请重新选择`)
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
    const filledTaskCount = getAllFilledFiles(group, scenario).length
    if (filledTaskCount === 0 || groupErrors[group.id]?.length) {
      return count
    }
    return count + filledTaskCount
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
      file.forEach((slotFile) => {
        fileMap.set(getUploadedFileIdentity(slotFile), slotFile)
      })
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

  const getDocumentId = (file: CompositeUploadedFile | undefined) => {
    if (!file) return undefined
    return params.uploadResults[file.id]?.document_id || file.documentId
  }

  getSubmittableCompositeGroups(params.groups, params.scenario).forEach(group => {
    const filledEntries = getFilledSlotEntries(group, params.scenario)
    const customPushName = (params.groupCustomPushNames[group.id] || '').trim() || getDefaultCompositeGroupPushName(group, params.scenario)

    if (customPushName) {
      filledEntries.forEach(([, files]) => {
        files.forEach((file) => {
          fileCustomPushNameMap[file.id] = customPushName
        })
      })
    }

    if (filledEntries.length >= 2) {
      const [primarySlotKey, primaryFiles] = filledEntries[0]
      const [pairedSlotKey, pairedFiles] = filledEntries[1]
      const primaryTemplateId = getEffectiveTemplateId(group, params.scenario, primarySlotKey)
      const pairedTemplateId = getEffectiveTemplateId(group, params.scenario, pairedSlotKey)
      const primaryDocumentId = getDocumentId(primaryFiles[0])
      const pairedDocumentId = getDocumentId(pairedFiles[0])

      if (primaryDocumentId && pairedDocumentId && primaryTemplateId && pairedTemplateId) {
        items.push({
          document_id: primaryDocumentId,
          template_id: primaryTemplateId,
          paired_document_id: pairedDocumentId,
          paired_template_id: pairedTemplateId,
          custom_push_name: customPushName || undefined,
        })
      }

      return
    }

    if (filledEntries.length === 1) {
      const [slotKey, files] = filledEntries[0]
      const templateId = getEffectiveTemplateId(group, params.scenario, slotKey)
      if (!templateId) {
        return
      }

      files.forEach((file) => {
        const documentId = getDocumentId(file)
        if (documentId) {
          items.push({
            document_id: documentId,
            template_id: templateId,
            custom_push_name: customPushName || undefined,
          })
        }
      })
    }
  })

  return { items, fileCustomPushNameMap }
}
