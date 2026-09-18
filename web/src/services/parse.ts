import api from './api'
import type { ParseResult, ProcessingJob } from '@/types'

export type ParseMode = 'pipeline' | 'vlm'

export interface CreateParseJobsPayload {
  document_ids: string[]
  parse_mode?: ParseMode
  language?: string
  enable_formula?: boolean
  enable_table?: boolean
  remove_watermark?: boolean
  watermark_keywords?: string[]
  page_ranges?: { target_pages?: string }
}

export interface CreateParseJobsResult {
  request_id: string
  job_ids: string[]
  status: string
  reused: boolean
  reuse_reason: string | null
}

export interface ListJobsParams {
  document_id?: string
  created_by?: string
  limit?: number
}

export const parseService = {
  /** 提交解析：一次请求为每个文档创建一个 Job（可选 Idempotency-Key 重试幂等） */
  async createJobs(
    payload: CreateParseJobsPayload,
    idempotencyKey?: string,
  ): Promise<CreateParseJobsResult> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
    const { data } = await api.post<{ success: boolean; data: CreateParseJobsResult }>(
      '/parse/jobs',
      payload,
      { headers },
    )
    return data.data
  },

  async getJob(jobId: string): Promise<ProcessingJob> {
    const { data } = await api.get<ProcessingJob>(`/jobs/${jobId}`)
    return data
  },

  async listJobs(params: ListJobsParams = {}): Promise<ProcessingJob[]> {
    const { data } = await api.get<{ success: boolean; data: ProcessingJob[] }>('/jobs', {
      params,
    })
    return data.data || []
  },

  async getDocumentParseResult(
    documentId: string,
  ): Promise<{ result_id: string; data: ParseResult }> {
    const { data } = await api.get<{ success: boolean; result_id: string; data: ParseResult }>(
      `/documents/${documentId}/parse-result`,
    )
    return { result_id: data.result_id, data: data.data }
  },
}

export default parseService
