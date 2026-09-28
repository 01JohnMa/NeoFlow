import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('./api', () => ({ default: apiMock }))

import { extractService } from './extract'

describe('extract service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('提交抽取并透传模板编码与文档', async () => {
    apiMock.post.mockResolvedValue({
      data: {
        success: true,
        data: {
          job_ids: ['job-1', 'job-2'],
          configuration_id: 'config-1',
          revision_id: 'revision-1',
          mode: 'published',
        },
      },
    })

    const result = await extractService.createJobs({
      template_code: 'inspection_report',
      document_ids: ['doc-a', 'doc-b'],
    })

    expect(apiMock.post).toHaveBeenCalledWith('/extract/jobs', {
      template_code: 'inspection_report',
      document_ids: ['doc-a', 'doc-b'],
    })
    expect(result.job_ids).toEqual(['job-1', 'job-2'])
    expect(result.mode).toBe('published')
    expect(result.revision_id).toBe('revision-1')
  })

  it('列出任务时默认带 capability=extract', async () => {
    apiMock.get.mockResolvedValue({ data: { success: true, data: [{ job_id: 'job-1' }] } })

    const jobs = await extractService.listJobs({ limit: 50 })

    expect(apiMock.get).toHaveBeenCalledWith('/jobs', {
      params: { capability: 'extract', limit: 50 },
    })
    expect(jobs).toHaveLength(1)
  })

  it('读取 Job 与按文档读取抽取结果', async () => {
    apiMock.get.mockResolvedValueOnce({ data: { job_id: 'job-1', status: 'processing' } })
    const job = await extractService.getJob('job-1')
    expect(apiMock.get).toHaveBeenCalledWith('/jobs/job-1')
    expect(job.status).toBe('processing')

    apiMock.get.mockResolvedValueOnce({
      data: {
        success: true,
        result_id: 'result-1',
        job_id: 'job-1',
        data: { name: '张三' },
        engine: { target: 'per_doc', schema_source: 'data_schema', usage: { requests: 1 } },
      },
    })
    const result = await extractService.getDocumentResult('doc-1')
    expect(apiMock.get).toHaveBeenCalledWith('/documents/doc-1/extract-result')
    expect(result.result_id).toBe('result-1')
    expect(result.engine?.usage?.requests).toBe(1)
  })

  it('按 Job 读取抽取结果', async () => {
    apiMock.get.mockResolvedValue({
      data: { success: true, result_id: 'result-2', job_id: 'job-2', data: [] },
    })

    const result = await extractService.getJobResult('job-2')

    expect(apiMock.get).toHaveBeenCalledWith('/jobs/job-2/extract-result')
    expect(result.data).toEqual([])
  })

})
