import type { ExtractSchema, ExtractSchemaUi } from './extractSchema'

// ============ Configuration Types ============

export type ConfigurationType = 'extract' | 'classify' | 'split' | 'composite'
export type ConfigurationStatus = 'draft' | 'published' | 'archived'
export type FieldType = 'text' | 'date' | 'number' | 'boolean'

export interface ConfigurationField {
  field_key: string
  field_label: string
  field_type: FieldType
  extraction_hint: string
  sort_order: number
  is_required: boolean
  default_value: string | null
  source_doc_type: string | null
}

export interface ConfigurationParseSection {
  backend?: string
  model_version?: 'pipeline' | 'vlm'
  method?: string
  effort?: string
  language?: string
  enable_formula?: boolean
  enable_table?: boolean
}

export interface ConfigurationDefinition {
  data_schema?: ExtractSchema
  target?: 'per_doc' | 'per_page'
  ui?: ExtractSchemaUi
  // Other operation types still have their own configuration sections.
  fields?: ConfigurationField[]
  extraction_prompt?: string | null
  parse?: ConfigurationParseSection
}

export interface ConfigurationRevision {
  id: string
  configuration_id: string
  revision_number: number
  definition: ConfigurationDefinition
  created_by: string | null
  created_at: string
  published_at: string | null
}

export interface Configuration {
  id: string
  tenant_id: string
  project_id: string
  name: string
  code: string | null
  description: string | null
  type: ConfigurationType
  status: ConfigurationStatus
  draft_definition: ConfigurationDefinition
  current_revision_id: string | null
  current_revision?: ConfigurationRevision | null
  created_at: string
  updated_at: string
}

export interface CreateConfigurationPayload {
  name: string
  tenant_id?: string
  project_id?: string
  code?: string | null
  description?: string | null
  type?: ConfigurationType
  definition?: Partial<ConfigurationDefinition>
}

export interface UpdateConfigurationPayload {
  name?: string
  code?: string | null
  description?: string | null
  type?: ConfigurationType
  definition?: Partial<ConfigurationDefinition>
}

export interface ConfigurationFieldPayload {
  field_key: string
  field_label: string
  field_type: FieldType
  extraction_hint?: string
  sort_order?: number
}

// ============ AI Template SDK types ============

export type SDKSessionState =
  | 'parsing'
  | 'parsed'
  | 'parse_failed'
  | 'analyzed'
  | 'template_confirmed'
  | 'prompt_generated'
  | 'committed'

export interface SDKDetectedField {
  field_key: string
  field_label: string
  field_type: 'text' | 'date' | 'number'
  extraction_hint: string
  sample_value?: string | null
}

export interface SDKDocumentAnalysis {
  detected_fields: SDKDetectedField[]
}

export interface SDKConfirmTemplatePayload {
  template_name: string
  template_code: string
  description?: string | null
  fields: SDKDetectedField[]
}

export interface SDKCommitResult {
  tenant_id: string
  configuration_id: string
  revision_id: string | null
  revision_number: number | null
  field_count: number
  status: 'draft'
}

export interface SDKSession {
  id: string
  file_name: string
  tenant_id: string
  template_name: string
  template_code: string
  instruction: string | null
  document_id: string
  parse_job_id: string
  parse_mode: 'pipeline' | 'vlm'
  parse_error: string | null
  parse_progress: number | null
  state: SDKSessionState
  analysis: SDKDocumentAnalysis | null
  confirmed_template: SDKConfirmTemplatePayload | null
  prompt: string | null
  commit_result: SDKCommitResult | null
}

// ============ Document types ============

// Document types
export interface Document {
  id: string
  user_id: string | null
  file_name: string
  original_file_name: string | null
  display_name: string | null
  custom_push_name: string | null
  file_path: string
  file_size: number | null
  file_type: string | null
  file_extension: string | null
  mime_type: string | null
  document_type: string | null
  status: DocumentStatus
  error_message: string | null
  created_at: string
  updated_at: string
  processed_at: string | null
}

export type DocumentStatus = 'pending' | 'uploaded' | 'queued' | 'processing' | 'completed' | 'failed'

// API Response types
export interface UploadResponse {
  document_id: string
  status: string
  message: string
  file_name: string
  file_size: number
  file_path: string
  created_at: string
}

export interface DocumentListResponse {
  items: Document[]
  total: number
  page: number
  limit: number
  has_more: boolean
}

// ============ Parse Result / Job types ============

export type ParseBlockType =
  | 'title'
  | 'text'
  | 'list'
  | 'table'
  | 'figure'
  | 'formula'
  | 'header'
  | 'footer'

export type ParseSource = 'native-text' | 'ocr' | 'vlm' | 'office-xml'

export type ParseCoordinateSpace = 'pixel' | 'normalized-1000'

export interface ParseBlock {
  id: string
  type: ParseBlockType
  bbox: number[]
  text: string | null
  table_html: string | null
  image_path: string | null
  latex: string | null
  source: ParseSource
  confidence: number | null
  reading_order: number
}

export interface ParsePage {
  page_no: number
  width: number
  height: number
  coordinate_space: ParseCoordinateSpace | string
  markdown: string | null
  blocks: ParseBlock[]
}

export interface ParseEngine {
  name?: string
  backend?: string
  effort?: string
  version?: string
  model_version?: string
  method?: string
}

export interface ParseResult {
  pages: ParsePage[]
  markdown: string
  engine: ParseEngine
  warnings: string[]
}

export interface ParseResultResponse {
  success: boolean
  result_id: string
  data: ParseResult
}

export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'

export interface ProcessingJob {
  job_id: string
  status: JobStatus | string
  stage: string
  progress: number
  document_ids: string[]
  error: string | null
  tenant_id: string | null
  configuration_revision_id: string | null
  execution_spec?: {
    capability?: string
    spec_version?: string
    document_id?: string
    effective_params?: { model_version?: string; [key: string]: unknown }
    policy_version?: string
    [key: string]: unknown
  } | null
  request_id?: string | null
  created_at: string
  updated_at: string
  finished_at?: string | null
}
