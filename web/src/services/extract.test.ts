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

  it('提交抽取并透传配置与文档', async () => {
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
      configuration_id: 'config-1',
      document_ids: ['doc-a', 'doc-b'],
    })

    expect(apiMock.post).toHaveBeenCalledWith('/extract/jobs', {
      configuration_id: 'config-1',
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

  it('管理员读取 extract 配置并规范化', async () => {
    apiMock.get.mockResolvedValue({
      data: [
        {
          id: 'config-1',
          name: '检测报告',
          code: 'quality_v1',
          status: 'published',
          type: 'extract',
          current_revision_id: 'revision-1',
          draft_definition: { target: 'per_doc', data_schema: { type: 'object' } },
        },
      ],
    })

    const configs = await extractService.listConfigurations()

    expect(apiMock.get).toHaveBeenCalledWith('/admin/configurations', {
      params: { type: 'extract' },
    })
    expect(configs).toHaveLength(1)
    expect(configs[0].draft_definition?.target).toBe('per_doc')
  })

  it('非管理员 403 时回退到已发布模板', async () => {
    apiMock.get
      .mockRejectedValueOnce(Object.assign(new Error('forbidden'), { response: { status: 403 } }))
      .mockResolvedValueOnce({
        data: [{ id: 'template-1', name: '旧版模板', code: 'legacy', description: null }],
      })

    const configs = await extractService.listConfigurations()

    expect(apiMock.get).toHaveBeenNthCalledWith(1, '/admin/configurations', {
      params: { type: 'extract' },
    })
    expect(apiMock.get).toHaveBeenNthCalledWith(2, '/tenants/me/templates')
    expect(configs[0]).toMatchObject({
      id: 'template-1',
      status: 'published',
      type: 'extract',
      current_revision_id: null,
    })
    expect(configs[0].draft_definition).toBeUndefined()
  })
})
