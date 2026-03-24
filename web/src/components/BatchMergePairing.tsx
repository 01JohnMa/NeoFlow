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
  disabled?: boolean
  onAddGroup: () => void
  onUpdateGroupFile: (groupId: string, slotKey: 'sphereFile' | 'distributionFile', file: File | null) => void
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
      templateId: 'light_distribution',
      templateCode: 'light_distribution',
    },
    {
      slotKey: 'sphereFile',
      label: '积分球',
      required: false,
      templateId: 'integrating_sphere',
      templateCode: 'integrating_sphere',
    },
  ],
  templateOptions: [
    { id: 'light_distribution', name: '光分布', code: 'light_distribution' },
    { id: 'integrating_sphere', name: '积分球', code: 'integrating_sphere' },
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
    templateSelections: {
      distributionFile: 'light_distribution',
      sphereFile: 'integrating_sphere',
    },
  }))
}

export function BatchMergePairing({
  groups,
  groupErrors = {},
  disabled = false,
  onAddGroup,
  onUpdateGroupFile,
  onRemoveGroup,
}: BatchMergePairingProps) {
  return (
    <CompositeGroupEditor
      scenario={lightingScenario}
      groups={toCompositeGroups(groups)}
      groupErrors={groupErrors}
      disabled={disabled}
      showTemplateSelector={false}
      onAddGroup={onAddGroup}
      onUpdateGroupTemplateSelection={() => {
        // legacy wrapper keeps template mapping fixed for old callers
      }}
      onUpdateGroupFile={(groupId, slotKey, file) => onUpdateGroupFile(groupId, slotKey as SlotKey, file)}
      onRemoveGroup={onRemoveGroup}
    />
  )
}

export type { UploadedFile, LightingGroup, SlotKey }
