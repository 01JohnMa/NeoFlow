export type CompositeSlotKey = string

export interface CompositeUploadedFile {
  id: string
  file: File
  documentId?: string
  filePath?: string
  preview: string | null
}

export interface CompositeGroup {
  id: string
  documents: Record<CompositeSlotKey, CompositeUploadedFile | null>
  templateSelections: Record<CompositeSlotKey, string | null>
}

export interface CompositeScenarioSlotDefinition {
  slotKey: CompositeSlotKey
  label: string
  templateCode?: string
  templateId?: string
  required: boolean
}

export interface CompositeTemplateOption {
  id: string
  name: string
  code: string
}

export type CompositePushNameStrategy = 'slotA-first' | 'slotB-first' | 'first-available'

export interface CompositeScenarioConfig {
  scenarioKey: string
  displayName: string
  description: string
  enabled: boolean
  maxGroups: number
  slotDefinitions: CompositeScenarioSlotDefinition[]
  templateOptions: CompositeTemplateOption[]
  pushNameStrategy: CompositePushNameStrategy
}

export interface CompositeGroupStatusSummary {
  empty: number
  complete: number
  partial: number
  totalTasks: number
}

export interface CompositeGroupValidationResult {
  canSubmit: boolean
  groupErrors: Record<string, string[]>
  globalErrors: string[]
  validTaskCount: number
}
