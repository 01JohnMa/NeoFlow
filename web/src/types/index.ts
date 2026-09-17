// ============ Configuration Types ============

export type ConfigurationType = 'parse' | 'extract' | 'classify' | 'split' | 'composite'
export type ConfigurationStatus = 'draft' | 'published' | 'archived'
export type ExtractionMode = 'ocr_llm' | 'vlm'
export type OutputMode = 'bitable' | 'excel_template' | 'both'
export type FieldType = 'text' | 'date' | 'number' | 'boolean'

export interface ConfigurationField {
  field_key: string
  field_label: string
  field_type: FieldType
  extraction_hint: string
  feishu_column: string
  sort_order: number
  review_enforced: boolean
  review_allowed_values: string[] | null
  is_required: boolean
  default_value: string | null
  source_doc_type: string | null
}

export interface FeishuOutputConfig {
  bitable_token: string | null
  table_id: string | null
}

export interface ExcelOutputConfig {
  file_name: string | null
  path: string | null
  placeholders: SDKExcelPlaceholder[]
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
  fields: ConfigurationField[]
  extraction_prompt: string | null
  extraction_mode: ExtractionMode
  output_mode: OutputMode
  push_attachment: boolean
  auto_approve: boolean
  feishu: FeishuOutputConfig
  excel: ExcelOutputConfig
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
  feishu_column?: string
  sort_order?: number
  review_enforced?: boolean
  review_allowed_values?: string[] | null
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
  review_enforced: boolean
  review_allowed_values: string[] | null
  sample_value?: string | null
}

export interface SDKExcelPlaceholder {
  sheet_name: string
  coordinate: string
  field_key: string
  raw_value: string
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
  revision_id: string
  revision_number: number
  field_count: number
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
  excel_template_file_name: string | null
  excel_placeholders: SDKExcelPlaceholder[]
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
  ocr_text: string | null
  ocr_confidence: number | null
  error_message: string | null
  created_at: string
  updated_at: string
  processed_at: string | null
}

export type DocumentStatus = 'pending' | 'uploaded' | 'queued' | 'processing' | 'pending_review' | 'completed' | 'failed'

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

export interface ProcessResponse {
  document_id: string
  job_id?: string
  status: string
  message: string
  estimated_time?: string
  success?: boolean
  document_type?: string
  extraction_data?: Record<string, unknown>
  ocr_confidence?: number
  processing_time?: number
  error?: string
}

export interface DocumentListResponse {
  items: Document[]
  total: number
  page: number
  limit: number
  has_more: boolean
}

export interface ReviewHintField {
  field_key: string
  field_label: string
  allowed_values: string[]
}

/** 后端 result 接口白名单字段，供详情页由 Configuration 驱动渲染 */
export interface ConfigurationFieldForDetail {
  field_key: string
  field_label: string
  field_type: 'text' | 'date' | 'number'
  is_required: boolean
  sort_order: number
  review_enforced: boolean
  review_allowed_values: string[] | null
  extraction_hint?: string
}

export interface ExtractionResultResponse {
  document_id: string
  document_type: string
  configuration_id?: string | null
  extraction_data: Record<string, unknown>
  ocr_text: string
  ocr_confidence: number | null
  created_at: string
  is_validated: boolean
  review_hint_fields?: ReviewHintField[]
  fields: ConfigurationFieldForDetail[]
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
  job_type: string
  status: JobStatus | string
  stage: string
  progress: number
  document_ids: string[]
  error: string | null
  tenant_id: string | null
  configuration_revision_id: string | null
  created_at: string
  updated_at: string
  finished_at?: string | null
}
