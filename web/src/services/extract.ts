import type { ExtractResultView } from '@/types/extractSchema'
import api from './api'
import type { ProcessingJob } from '@/types'

export interface CreateExtractJobsPayload {
  template_code: string
  document_ids: string[]
}

export interface CreateExtractJobsResult {
  job_ids: string[]
  template_code: string
  revision_id: string | null
  mode: 'published'
}

export interface ExtractEngine {
  name?: string
  target?: string
  schema_source?: string
  schema_hash?: string
  prompt_version?: string
  attempts?: number
  usage?: {
    requests?: number
    input_tokens?: number | null
    output_tokens?: number | null
  }
  [key: string]: unknown
}

export interface ExtractResultResponse {
  success: boolean
  result_id: string
  job_id: string
  data: unknown
  engine?: ExtractEngine | null
  view?: ExtractResultView | null
}

export interface ExtractConfigurationDefinition {
  target?: string
  data_schema?: unknown
  extraction_strategy?: 'full_document' | 'source_page_routed' | 'agentic_source_page_routed'
}

export interface ExtractConfiguration {
  id: string
  name: string
  code: string | null
  status: 'draft' | 'published' | 'archived'
  type: string
  current_revision_id: string | null
  /** Configuration detail is available only in internal administration views. */
  draft_definition?: ExtractConfigurationDefinition | null
  description?: string | null
}

export interface ListExtractJobsParams {
  document_id?: string
  created_by?: string
  limit?: number
  capability?: string
}

export const extractService = {
  /** 提交抽取：一次请求为每个文档创建一个 Extract Job */
  async createJobs(payload: CreateExtractJobsPayload): Promise<CreateExtractJobsResult> {
    const { data } = await api.post<{ success: boolean; data: CreateExtractJobsResult }>(
      '/extract/jobs',
      payload,
    )
    return data.data
  },

  async getJob(jobId: string): Promise<ProcessingJob> {
    const { data } = await api.get<ProcessingJob>(`/jobs/${jobId}`)
    return data
  },

  async listJobs(params: ListExtractJobsParams = {}): Promise<ProcessingJob[]> {
    const { data } = await api.get<{ success: boolean; data: ProcessingJob[] }>('/jobs', {
      params: { capability: 'extract', ...params },
    })
    return data.data || []
  },

  async getDocumentResult(documentId: string): Promise<ExtractResultResponse> {
    const { data } = await api.get<ExtractResultResponse>(
      `/documents/${documentId}/extract-result`,
    )
    return data
  },

  async getJobResult(jobId: string): Promise<ExtractResultResponse> {
    const { data } = await api.get<ExtractResultResponse>(`/jobs/${jobId}/extract-result`)
    return data
  },

}

export default extractService
