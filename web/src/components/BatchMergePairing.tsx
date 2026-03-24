import { CompositeGroupEditor } from '@/features/composite-upload/components/CompositeGroupEditor'
import type { CompositeGroup, CompositeScenarioConfig, CompositeUploadedFile } from '@/features/composite-upload/core/types'

type UploadedFile = CompositeUploadedFile

interface LightingGroup {
  id: string
  sphereFile: UploadedFile | null
  distributionFile: UploadedFile | null
}

interface BatchMergePairingProps {
  groups: LightingGroup[]
  groupErrors?: Record<string, string[]>
  groupCustomPushNames?: Record<string, string>
  groupEffectivePushNames?: Record<string, string>
  disabled?: boolean
  onAddGroup: () => void
  onUpdateGroupFile: (groupId: string, slotKey: 'sphereFile' | 'distributionFile', file: File | null) => void
  onUpdateGroupCustomPushName: (groupId: string, value: string) => void
  onApplyGroupRecommendedName: (groupId: string) => void
  onRemoveGroup: (groupId: string) => void
}

type SlotKey = 'sphereFile' | 'distributionFile'

const lightingScenario: CompositeScenarioConfig = {
  scenarioKey: 'lighting_pair_legacy',
  displayName: '照明分组上传',
  description: '按组填写积分球与光分布文件。支持完整双文件组，也支持仅上传单侧文件。',
  enabled: true,
  maxGroups: 5,
  slotDefinitions: [
    {
      slotKey: 'distributionFile',
      label: '光分布',
      required: false,
    },
    {
      slotKey: 'sphereFile',
      label: '积分球',
      required: false,
    },
  ],
  pushNameStrategy: 'slotA-first',
}

function toCompositeGroups(groups: LightingGroup[]): CompositeGroup[] {
  return groups.map(group => ({
    id: group.id,
    documents: {
      distributionFile: group.distributionFile,
      sphereFile: group.sphereFile,
    },
  }))
}

export function BatchMergePairing({
  groups,
  groupErrors = {},
  groupCustomPushNames = {},
  groupEffectivePushNames = {},
  disabled = false,
  onAddGroup,
  onUpdateGroupFile,
  onUpdateGroupCustomPushName,
  onApplyGroupRecommendedName,
  onRemoveGroup,
}: BatchMergePairingProps) {
  return (
    <CompositeGroupEditor
      scenario={lightingScenario}
      groups={toCompositeGroups(groups)}
      groupErrors={groupErrors}
      groupCustomPushNames={groupCustomPushNames}
      groupEffectivePushNames={groupEffectivePushNames}
      disabled={disabled}
      onAddGroup={onAddGroup}
      onUpdateGroupFile={(groupId, slotKey, file) => onUpdateGroupFile(groupId, slotKey as SlotKey, file)}
      onUpdateGroupCustomPushName={onUpdateGroupCustomPushName}
      onApplyGroupRecommendedName={onApplyGroupRecommendedName}
      onRemoveGroup={onRemoveGroup}
    />
  )
}

export type { UploadedFile, LightingGroup, SlotKey }
