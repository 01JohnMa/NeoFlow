import type { ExtractResultView } from '@/types/extractSchema'
import api from './api'
import type { ProcessingJob } from '@/types'

export interface CreateExtractJobsPayload {
  configuration_id: string
  document_ids: string[]
}

export interface CreateExtractJobsResult {
  job_ids: string[]
  configuration_id: string
  revision_id: string | null
  mode: 'published' | 'draft'
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
  /** 旧版模板（/tenants/me/templates）不返回定义，此时缺失 */
  draft_definition?: ExtractConfigurationDefinition | null
  description?: string | null
}

export interface ListExtractJobsParams {
  document_id?: string
  created_by?: string
  limit?: number
  capability?: string
}

function isForbidden(error: unknown): boolean {
  return (error as { response?: { status?: number } })?.response?.status === 403
}

function normalizeAdminConfiguration(row: Record<string, unknown>): ExtractConfiguration {
  return {
    id: String(row.id),
    name: String(row.name ?? ''),
    code: (row.code as string | null) ?? null,
    status: (row.status as ExtractConfiguration['status']) ?? 'draft',
    type: String(row.type ?? 'extract'),
    current_revision_id: (row.current_revision_id as string | null) ?? null,
    draft_definition:
      (row.draft_definition as ExtractConfigurationDefinition | null) ?? undefined,
    description: (row.description as string | null) ?? null,
  }
}

function normalizeTemplate(row: Record<string, unknown>): ExtractConfiguration {
  const extractionStrategy = row.extraction_strategy === 'agentic_source_page_routed'
    ? 'agentic_source_page_routed'
    : row.extraction_strategy === 'source_page_routed'
      ? 'source_page_routed'
      : 'full_document'
  return {
    id: String(row.id),
    name: String(row.name ?? ''),
    code: (row.code as string | null) ?? null,
    status: 'published',
    type: 'extract',
    current_revision_id: null,
    draft_definition: { extraction_strategy: extractionStrategy },
    description: (row.description as string | null) ?? null,
  }
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

  /** 管理员走 /admin/configurations?type=extract；非管理员 403 时回退到已发布模板 */
  async listConfigurations(): Promise<ExtractConfiguration[]> {
    try {
      const { data } = await api.get<Record<string, unknown>[]>('/admin/configurations', {
        params: { type: 'extract' },
      })
      return (data || []).map(normalizeAdminConfiguration)
    } catch (error) {
      if (!isForbidden(error)) throw error
      const { data } = await api.get<Record<string, unknown>[]>('/tenants/me/templates')
      return (data || []).map(normalizeTemplate)
    }
  },
}

export default extractService
