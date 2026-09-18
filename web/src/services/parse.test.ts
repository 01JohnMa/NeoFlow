import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('./api', () => ({ default: apiMock }))

import { parseService } from './parse'

describe('parse service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('提交解析并透传幂等键', async () => {
    apiMock.post.mockResolvedValue({
      data: {
        success: true,
        data: {
          request_id: 'req-1',
          job_ids: ['job-1', 'job-2'],
          status: 'ok',
          reused: false,
          reuse_reason: null,
        },
      },
    })

    const result = await parseService.createJobs(
      { document_ids: ['doc-a', 'doc-b'], parse_mode: 'vlm', page_ranges: { target_pages: '1-3' } },
      'K1',
    )

    expect(apiMock.post).toHaveBeenCalledWith(
      '/parse/jobs',
      { document_ids: ['doc-a', 'doc-b'], parse_mode: 'vlm', page_ranges: { target_pages: '1-3' } },
      { headers: { 'Idempotency-Key': 'K1' } },
    )
    expect(result.job_ids).toEqual(['job-1', 'job-2'])
    expect(result.reused).toBe(false)
  })

  it('缺省幂等键时不带请求头', async () => {
    apiMock.post.mockResolvedValue({
      data: { success: true, data: { request_id: 'r', job_ids: ['j'], status: 'ok', reused: false, reuse_reason: null } },
    })

    await parseService.createJobs({ document_ids: ['doc-a'] })

    expect(apiMock.post).toHaveBeenCalledWith('/parse/jobs', { document_ids: ['doc-a'] }, { headers: undefined })
  })

  it('透传高级解析参数', async () => {
    apiMock.post.mockResolvedValue({
      data: { success: true, data: { request_id: 'r', job_ids: ['j'], status: 'ok', reused: false, reuse_reason: null } },
    })

    await parseService.createJobs({
      document_ids: ['doc-a'],
      language: 'en',
      enable_formula: false,
      enable_table: true,
      remove_watermark: true,
      watermark_keywords: ['COPY', '样本'],
    })

    expect(apiMock.post).toHaveBeenCalledWith(
      '/parse/jobs',
      {
        document_ids: ['doc-a'],
        language: 'en',
        enable_formula: false,
        enable_table: true,
        remove_watermark: true,
        watermark_keywords: ['COPY', '样本'],
      },
      { headers: undefined },
    )
  })

  it('读取 Job 与按文档读取 Parse 结果', async () => {
    apiMock.get.mockResolvedValueOnce({ data: { job_id: 'job-1', status: 'processing' } })
    const job = await parseService.getJob('job-1')
    expect(apiMock.get).toHaveBeenCalledWith('/jobs/job-1')
    expect(job.status).toBe('processing')

    apiMock.get.mockResolvedValueOnce({
      data: { success: true, result_id: 'result-1', data: { pages: [], markdown: '' } },
    })
    const result = await parseService.getDocumentParseResult('doc-1')
    expect(apiMock.get).toHaveBeenCalledWith('/documents/doc-1/parse-result')
    expect(result.result_id).toBe('result-1')
  })

  it('列出我的解析任务', async () => {
    apiMock.get.mockResolvedValue({ data: { success: true, data: [{ job_id: 'job-1' }] } })

    const jobs = await parseService.listJobs({ created_by: 'user-1', limit: 50 })

    expect(apiMock.get).toHaveBeenCalledWith('/jobs', { params: { created_by: 'user-1', limit: 50 } })
    expect(jobs).toHaveLength(1)
  })
})
