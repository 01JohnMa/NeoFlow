/** Execution JSON Schema subset. Builder support is intentionally narrower. */
export interface ExtractSchema {
  type?: string | string[]
  properties?: Record<string, ExtractSchema>
  items?: ExtractSchema
  required?: string[]
  enum?: unknown[]
  description?: string
  format?: string
  additionalProperties?: boolean
  [keyword: string]: unknown
}

/** Presentation only: never type, enum, required, hints, or default values. */
export type ExtractSchemaUi = Record<string, { label?: string; order?: number }>

export interface ExtractAuthoringDefinition {
  data_schema: ExtractSchema
  target?: 'per_doc' | 'per_page'
  ui?: ExtractSchemaUi
  extraction_strategy?: 'full_document' | 'page_routed'
}

export type ExtractResultView =
  | { status: 'unavailable'; reason: string }
  | {
      status: 'available'
      origin: 'execution_spec' | 'revision'
      target: 'per_doc' | 'per_page'
      schema: ExtractSchema
      schema_hash: string
      ui: ExtractSchemaUi
    }
