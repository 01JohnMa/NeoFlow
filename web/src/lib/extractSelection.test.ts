import { describe, expect, it } from 'vitest'
import type { ExtractConfiguration } from '@/services/extract'
import type { ProcessingJob } from '@/types'
import {
  buildHistoryResultRef,
  buildResultRefs,
  configurationDefinitionPreview,
  resolveResultTarget,
  resultMatchesJob,
  selectableConfigurations,
} from '@/lib/extractSelection'

function makeConfig(
  overrides: Pick<ExtractConfiguration, 'id' | 'status'> & Partial<ExtractConfiguration>,
): ExtractConfiguration {
  return {
    name: overrides.id,
    code: null,
    type: 'extract',
    current_revision_id: null,
    ...overrides,
  }
}

function makeJob(overrides: Partial<ProcessingJob>): ProcessingJob {
  return {
    job_id: 'job-1',
    status: 'completed',
    stage: 'extract',
    progress: 100,
    document_ids: ['doc-a'],
    error: null,
    tenant_id: null,
    configuration_revision_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('buildResultRefs', () => {
  it('按索引把 document_ids 与 job_ids 配对，每个结果项自带 jobId', () => {
    expect(buildResultRefs(['doc-a', 'doc-b'], ['job-1', 'job-2'])).toEqual([
      { documentId: 'doc-a', jobId: 'job-1' },
      { documentId: 'doc-b', jobId: 'job-2' },
    ])
  })

  it('缺少 job_id 的文档不产生可选项，不猜测、不回退', () => {
    expect(buildResultRefs(['doc-a', 'doc-b', 'doc-c'], ['job-1'])).toEqual([
      { documentId: 'doc-a', jobId: 'job-1' },
    ])
  })
})

describe('resolveResultTarget', () => {
  const refs = buildResultRefs(['doc-a', 'doc-b'], ['job-1', 'job-2'])

  it('切换文档时保留各自的 jobId', () => {
    expect(resolveResultTarget(refs, 'job-2')).toEqual({ documentId: 'doc-b', jobId: 'job-2' })
    expect(resolveResultTarget(refs, 'job-1')).toEqual({ documentId: 'doc-a', jobId: 'job-1' })
  })

  it('selectedJobId 不在结果列表中时返回 null', () => {
    expect(resolveResultTarget(refs, 'job-other')).toBeNull()
    expect(resolveResultTarget(refs, null)).toBeNull()
    expect(resolveResultTarget([], 'job-1')).toBeNull()
  })
})

describe('buildHistoryResultRef', () => {
  it('History / ?job= 恢复使用该 Job 与其首个文档', () => {
    const job = makeJob({ job_id: 'job-9', document_ids: ['doc-z', 'doc-y'] })
    expect(buildHistoryResultRef(job)).toEqual({ documentId: 'doc-z', jobId: 'job-9' })
  })

  it('任务没有文档时不可恢复', () => {
    expect(buildHistoryResultRef(makeJob({ document_ids: [] }))).toBeNull()
  })
})

describe('resultMatchesJob', () => {
  it('结果 job_id 与所选 Job 一致才允许展示', () => {
    expect(resultMatchesJob({ job_id: 'job-1' }, 'job-1')).toBe(true)
  })

  it('结果 job_id 不一致、缺失结果或未选 Job 时拒绝展示', () => {
    expect(resultMatchesJob({ job_id: 'job-other' }, 'job-1')).toBe(false)
    expect(resultMatchesJob(null, 'job-1')).toBe(false)
    expect(resultMatchesJob({ job_id: 'job-1' }, null)).toBe(false)
  })
})

describe('selectableConfigurations', () => {
  it('排除已归档配置', () => {
    const configs = [
      makeConfig({ id: 'c1', status: 'draft' }),
      makeConfig({ id: 'c2', status: 'published' }),
      makeConfig({ id: 'c3', status: 'archived' }),
    ]
    expect(selectableConfigurations(configs).map((config) => config.id)).toEqual(['c1', 'c2'])
  })
})

describe('configurationDefinitionPreview', () => {
  it('有 data_schema 时返回 schema 预览', () => {
    const preview = configurationDefinitionPreview({
      draft_definition: { data_schema: { type: 'object' } },
    })
    expect(preview).toEqual({ kind: 'schema', schema: { type: 'object' } })
  })

  it('仅 fields 非空时才按旧版配置展示字段数', () => {
    expect(configurationDefinitionPreview({ draft_definition: { fields: [1, 2] } })).toEqual({
      kind: 'legacy',
      fieldCount: 2,
    })
    expect(configurationDefinitionPreview({ draft_definition: { fields: [] } })).toEqual({
      kind: 'empty',
    })
  })

  it('draft_definition 缺失时按已发布模板处理', () => {
    expect(configurationDefinitionPreview({ draft_definition: null })).toEqual({
      kind: 'published-template',
    })
    expect(configurationDefinitionPreview(null)).toEqual({ kind: 'published-template' })
  })

  it('draft_definition 为空对象时提示没有可预览的定义', () => {
    expect(configurationDefinitionPreview({ draft_definition: {} })).toEqual({ kind: 'empty' })
  })
})
