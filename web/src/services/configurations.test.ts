import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))

vi.mock('./api', () => ({ api: apiMock }))

import * as configurationsApi from './configurations'

describe('configurations service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('按租户过滤列出配置', async () => {
    apiMock.get.mockResolvedValue({ data: [{ id: 'config-1' }] })

    const result = await configurationsApi.listConfigurations({ tenant_id: 'tenant-1' })

    expect(apiMock.get).toHaveBeenCalledWith('/admin/configurations', {
      params: { tenant_id: 'tenant-1' },
    })
    expect(result).toEqual([{ id: 'config-1' }])
  })

  it('创建配置并解包 data', async () => {
    apiMock.post.mockResolvedValue({ data: { success: true, data: { id: 'config-1' } } })

    const result = await configurationsApi.createConfiguration({
      name: '检测报告',
      tenant_id: 'tenant-1',
    })

    expect(apiMock.post).toHaveBeenCalledWith('/admin/configurations', {
      name: '检测报告',
      tenant_id: 'tenant-1',
    })
    expect(result).toEqual({ id: 'config-1' })
  })

  it('更新配置 definition 并解包 data', async () => {
    apiMock.put.mockResolvedValue({
      data: { success: true, data: { id: 'config-1', status: 'draft' } },
    })

    const result = await configurationsApi.updateConfiguration('config-1', {
      definition: { fields: [] },
    })

    expect(apiMock.put).toHaveBeenCalledWith('/admin/configurations/config-1', {
      definition: { fields: [] },
    })
    expect(result).toEqual({ id: 'config-1', status: 'draft' })
  })

  it('发布配置返回 configuration 与 revision', async () => {
    const payload = {
      success: true,
      data: {
        configuration: { id: 'config-1', status: 'published' },
        revision: { id: 'revision-1', revision_number: 2 },
      },
    }
    apiMock.post.mockResolvedValue({ data: payload })

    const result = await configurationsApi.publishConfiguration('config-1')

    expect(apiMock.post).toHaveBeenCalledWith('/admin/configurations/config-1/publish')
    expect(result.configuration.status).toBe('published')
    expect(result.revision.revision_number).toBe(2)
  })

  it('归档配置并解包 data', async () => {
    apiMock.post.mockResolvedValue({
      data: { success: true, data: { id: 'config-1', status: 'archived' } },
    })

    const result = await configurationsApi.archiveConfiguration('config-1')

    expect(apiMock.post).toHaveBeenCalledWith('/admin/configurations/config-1/archive')
    expect(result.status).toBe('archived')
  })

  it('补字段示例并解包 configuration/revision', async () => {
    apiMock.post.mockResolvedValue({
      data: {
        success: true,
        data: {
          configuration: { id: 'config-1', status: 'published' },
          revision: { id: 'revision-2', revision_number: 2 },
        },
      },
    })

    const result = await configurationsApi.appendFieldExample('config-1', 'sample_name', 'LED 灯')

    expect(apiMock.post).toHaveBeenCalledWith(
      '/admin/configurations/config-1/fields/sample_name/examples',
      { example: 'LED 灯' },
    )
    expect(result.configuration.status).toBe('published')
    expect(result.revision?.revision_number).toBe(2)
  })

  it('列出与读取修订', async () => {
    apiMock.get.mockResolvedValueOnce({ data: [{ id: 'revision-1' }] })
    const revisions = await configurationsApi.listRevisions('config-1')
    expect(apiMock.get).toHaveBeenCalledWith('/admin/configurations/config-1/revisions')
    expect(revisions).toEqual([{ id: 'revision-1' }])

    apiMock.get.mockResolvedValueOnce({ data: { id: 'revision-1' } })
    const revision = await configurationsApi.getRevision('config-1', 'revision-1')
    expect(apiMock.get).toHaveBeenCalledWith(
      '/admin/configurations/config-1/revisions/revision-1',
    )
    expect(revision).toEqual({ id: 'revision-1' })
  })
})
