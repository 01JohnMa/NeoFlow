// Document types
export interface Document {
  id: string
  user_id: string | null
  file_name: string
  original_file_name: string | null
  display_name: string | null  // 规范化显示名称
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

// Extraction Results
export interface InspectionReport {
  id: string
  document_id: string
  sample_name: string | null
  specification_model: string | null
  production_date_batch: string | null
  inspected_unit_name: string | null
  inspected_unit_address: string | null
  inspected_unit_phone: string | null
  manufacturer_name: string | null
  manufacturer_address: string | null
  manufacturer_phone: string | null
  task_source: string | null
  sampling_agency: string | null
  sampling_date: string | null
  inspection_conclusion: string | null
  inspection_category: string | null
  notes: string | null
  inspector: string | null
  reviewer: string | null
  approver: string | null
  extraction_confidence: number | null
  raw_extraction_data: Record<string, unknown> | null
  is_validated: boolean
  validated_by: string | null
  validated_at: string | null
  validation_notes: string | null
  created_at: string
  updated_at: string
}

export interface Express {
  id: string
  document_id: string
  tracking_number: string | null
  recipient: string | null
  delivery_address: string | null
  sender: string | null
  sender_address: string | null
  notes: string | null
  extraction_confidence: number | null
  raw_extraction_data: Record<string, unknown> | null
  is_validated: boolean
  validated_by: string | null
  validated_at: string | null
  validation_notes: string | null
  created_at: string
  updated_at: string
}

export interface SamplingForm {
  id: string
  document_id: string
  task_source: string | null
  task_category: string | null
  manufacturer: string | null
  sample_name: string | null
  specification_model: string | null
  production_date_batch: string | null
  sample_storage_location: string | null
  sampling_channel: string | null
  sampling_unit: string | null
  sampling_date: string | null
  sampled_province: string | null
  sampled_city: string | null
  extraction_confidence: number | null
  raw_extraction_data: Record<string, unknown> | null
  is_validated: boolean
  validated_by: string | null
  validated_at: string | null
  validation_notes: string | null
  created_at: string
  updated_at: string
}

export interface LightingReport {
  id: string
  document_id: string
  // 来自积分球（14个字段）
  sample_model: string | null           // 样品型号
  chromaticity_x: string | null         // 色品坐标X
  chromaticity_y: string | null         // 色品坐标Y
  duv: string | null                    // duv
  cct: string | null                    // 色温(CCT)
  ra: string | null                     // Ra
  r9: string | null                     // R9
  cqs: string | null                    // CQS
  sdcm: string | null                   // 色容差SDCM
  power_sphere: string | null           // 功率(积分球)
  luminous_flux_sphere: string | null   // 光通量(积分球)
  luminous_efficacy_sphere: string | null // 光效(积分球)
  rf: string | null                     // Rf
  rg: string | null                     // Rg
  // 来自光分布（6个字段）
  lamp_specification: string | null     // 灯具规格
  power: string | null                  // 功率
  luminous_flux: string | null          // 光通量(光分布)
  luminous_efficacy: string | null      // 光效(光分布)
  peak_intensity: string | null         // 峰值光强
  beam_angle: string | null             // 光束角
  // 元数据
  extraction_confidence: number | null
  raw_extraction_data: Record<string, unknown> | null
  is_validated: boolean
  validated_by: string | null
  validated_at: string | null
  validation_notes: string | null
  created_at: string
  updated_at: string
}

export type ExtractionResult = InspectionReport | Express | SamplingForm | LightingReport

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

export interface ExtractionResultResponse {
  document_id: string
  document_type: string
  extraction_data: ExtractionResult
  ocr_text: string
  ocr_confidence: number | null
  created_at: string
  is_validated: boolean
}

// Field definitions for editing
export interface FieldDefinition {
  key: string
  label: string
  type: 'text' | 'textarea' | 'date' | 'number'
  required?: boolean
}

export const INSPECTION_REPORT_FIELDS: FieldDefinition[] = [
  { key: 'sample_name', label: '样品名称', type: 'text' },
  { key: 'specification_model', label: '规格型号', type: 'text' },
  { key: 'production_date_batch', label: '生产日期/批次', type: 'text' },
  { key: 'inspected_unit_name', label: '被检单位名称', type: 'text' },
  { key: 'inspected_unit_address', label: '被检单位地址', type: 'text' },
  { key: 'inspected_unit_phone', label: '被检单位电话', type: 'text' },
  { key: 'manufacturer_name', label: '生产企业名称', type: 'text' },
  { key: 'manufacturer_address', label: '生产企业地址', type: 'text' },
  { key: 'manufacturer_phone', label: '生产企业电话', type: 'text' },
  { key: 'task_source', label: '任务来源', type: 'text' },
  { key: 'sampling_agency', label: '抽样机构', type: 'text' },
  { key: 'sampling_date', label: '抽样日期', type: 'date' },
  { key: 'inspection_conclusion', label: '检验结论', type: 'text' },
  { key: 'inspection_category', label: '检验类别', type: 'text' },
  { key: 'inspector', label: '检验员', type: 'text' },
  { key: 'reviewer', label: '审核员', type: 'text' },
  { key: 'approver', label: '批准人', type: 'text' },
  { key: 'notes', label: '备注', type: 'textarea' },
]

export const EXPRESS_FIELDS: FieldDefinition[] = [
  { key: 'tracking_number', label: '运单号', type: 'text' },
  { key: 'sender', label: '寄件人', type: 'text' },
  { key: 'sender_address', label: '寄件地址', type: 'textarea' },
  { key: 'recipient', label: '收件人', type: 'text' },
  { key: 'delivery_address', label: '收件地址', type: 'textarea' },
  { key: 'notes', label: '备注', type: 'textarea' },
]

export const SAMPLING_FORM_FIELDS: FieldDefinition[] = [
  { key: 'task_source', label: '任务来源', type: 'text' },
  { key: 'task_category', label: '任务类别', type: 'text' },
  { key: 'manufacturer', label: '生产企业', type: 'text' },
  { key: 'sample_name', label: '样品名称', type: 'text' },
  { key: 'specification_model', label: '规格型号', type: 'text' },
  { key: 'production_date_batch', label: '生产日期/批号', type: 'text' },
  { key: 'sample_storage_location', label: '备样封存地点', type: 'text' },
  { key: 'sampling_channel', label: '抽样渠道', type: 'text' },
  { key: 'sampling_unit', label: '抽样单位', type: 'text' },
  { key: 'sampling_date', label: '抽样日期', type: 'date' },
  { key: 'sampled_province', label: '被抽检省份', type: 'text' },
  { key: 'sampled_city', label: '被抽检市', type: 'text' },
]

export const LIGHTING_REPORT_FIELDS: FieldDefinition[] = [
  // 来自积分球（14个字段）
  { key: 'sample_model', label: '样品型号', type: 'text' },
  { key: 'chromaticity_x', label: '色品坐标X', type: 'text' },
  { key: 'chromaticity_y', label: '色品坐标Y', type: 'text' },
  { key: 'duv', label: 'Duv', type: 'text' },
  { key: 'cct', label: '色温(CCT)', type: 'text' },
  { key: 'ra', label: 'Ra', type: 'text' },
  { key: 'r9', label: 'R9', type: 'text' },
  { key: 'cqs', label: 'CQS', type: 'text' },
  { key: 'sdcm', label: '色容差SDCM', type: 'text' },
  { key: 'power_sphere', label: '功率(积分球)', type: 'text' },
  { key: 'luminous_flux_sphere', label: '光通量(积分球)', type: 'text' },
  { key: 'luminous_efficacy_sphere', label: '光效(积分球)', type: 'text' },
  { key: 'rf', label: 'Rf', type: 'text' },
  { key: 'rg', label: 'Rg', type: 'text' },
  // 来自光分布（6个字段）
  { key: 'lamp_specification', label: '灯具规格', type: 'text' },
  { key: 'power', label: '功率', type: 'text' },
  { key: 'luminous_flux', label: '光通量(光分布)', type: 'text' },
  { key: 'luminous_efficacy', label: '光效(光分布)', type: 'text' },
  { key: 'peak_intensity', label: '峰值光强', type: 'text' },
  { key: 'beam_angle', label: '光束角', type: 'text' },
]


