import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
}))

vi.mock('./api', () => ({ api: apiMock }))

import * as jobsApi from './jobs'

describe('jobs service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('按 ID 读取任务', async () => {
    apiMock.get.mockResolvedValue({ data: { job_id: 'job-1', status: 'completed' } })

    const job = await jobsApi.getJob('job-1')

    expect(apiMock.get).toHaveBeenCalledWith('/jobs/job-1')
    expect(job.job_id).toBe('job-1')
  })

  it('读取 ParseResult 并解包 data', async () => {
    const parseData = { pages: [], markdown: '# Demo', engine: {}, warnings: [] }
    apiMock.get.mockResolvedValue({
      data: { success: true, result_id: 'result-1', data: parseData },
    })

    const result = await jobsApi.getParseResult('job-1')

    expect(apiMock.get).toHaveBeenCalledWith('/jobs/job-1/parse-result')
    expect(result).toEqual(parseData)
  })
})
