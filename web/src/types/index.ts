// ============ Admin Config Types ============

export interface TemplateField {
  id: string
  template_id: string
  field_key: string
  field_label: string
  field_type: 'text' | 'date' | 'number'
  extraction_hint: string | null
  feishu_column: string | null
  sort_order: number
  review_enforced: boolean
  review_allowed_values: string[] | null
}

export interface TemplateExample {
  id: string
  template_id: string
  example_input: string
  example_output: Record<string, unknown>
  sort_order: number
  is_active: boolean
}

export interface AdminTemplate {
  id: string
  tenant_id: string
  name: string
  code: string
  description: string | null
  required_doc_count: number
  sort_order: number
  is_active: boolean
  auto_approve: boolean
  push_attachment: boolean
  extraction_mode: 'ocr_llm' | 'vlm'
  feishu_bitable_token: string | null
  feishu_table_id: string | null
}

export interface CreateFieldPayload {
  field_key: string
  field_label: string
  field_type: 'text' | 'date' | 'number'
  extraction_hint?: string
  feishu_column?: string
  sort_order?: number
  review_enforced?: boolean
  review_allowed_values?: string[] | null
}

export interface UpdateFieldPayload extends Partial<CreateFieldPayload> {}

export interface CreateExamplePayload {
  example_input: string
  example_output: Record<string, unknown>
  sort_order?: number
  is_active?: boolean
}

export interface UpdateExamplePayload extends Partial<CreateExamplePayload> {}

export interface UpdateTemplateConfigPayload {
  feishu_bitable_token?: string
  feishu_table_id?: string
  auto_approve?: boolean
  push_attachment?: boolean
  extraction_mode?: 'ocr_llm' | 'vlm'
}

export interface ReorderItem {
  id: string
  sort_order: number
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

export type DocumentStatus = 'pending' | 'uploaded' | 'processing' | 'pending_review' | 'completed' | 'failed'

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

/** 后端 result 接口白名单字段，供详情页纯模板驱动渲染 */
export interface TemplateFieldForDetail {
  field_key: string
  field_label: string
  field_type: 'text' | 'date' | 'number'
  is_required: boolean
  sort_order: number
  review_enforced: boolean
  review_allowed_values: string[] | null
}

export interface ExtractionResultResponse {
  document_id: string
  document_type: string
  extraction_data: Record<string, unknown>
  ocr_text: string
  ocr_confidence: number | null
  created_at: string
  is_validated: boolean
  review_hint_fields?: ReviewHintField[]
  template_fields: TemplateFieldForDetail[]
}

// ============ Batch types ============

export interface BatchProcessItem {
  document_id: string
  template_id: string
  paired_document_id?: string
  paired_template_id?: string
  custom_push_name?: string
}

export interface BatchJobItemStatus {
  index: number
  type: 'single' | 'merge'
  document_ids: string[]
  status: 'pending' | 'processing' | 'completed' | 'failed'
  error?: string
}

export interface BatchJobStatus {
  job_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  stage: string
  progress: number
  document_ids: string[]
  error: string | null
  items?: BatchJobItemStatus[]
  total?: number
  completed_count?: number
}



