import type { ExtractConfiguration, ExtractResultResponse } from '@/services/extract'
import type { ProcessingJob } from '@/types'

/** 结果选择项：文档与创建它的 Job 必须成对出现，结果只按 jobId 读取 */
export interface ResultRef {
  documentId: string
  jobId: string
}

/** 一次 Run 的 document_ids 与返回的 job_ids 按索引配对（仅保留有 jobId 的项） */
export function buildResultRefs(documentIds: string[], jobIds: string[]): ResultRef[] {
  const refs: ResultRef[] = []
  documentIds.forEach((documentId, index) => {
    const jobId = jobIds[index]
    if (jobId) refs.push({ documentId, jobId })
  })
  return refs
}

/** History / ?job= 恢复：只取该 Job 的首个文档，且必须保留 jobId */
export function buildHistoryResultRef(job: ProcessingJob): ResultRef | null {
  const documentId = job.document_ids?.[0]
  if (!documentId || !job.job_id) return null
  return { documentId, jobId: job.job_id }
}

/** 根据 selectedJobId 定位当前结果；找不到对应 Job 时返回 null，绝不回退到文档最新结果 */
export function resolveResultTarget(
  refs: ResultRef[],
  selectedJobId: string | null,
): ResultRef | null {
  if (!selectedJobId) return null
  return refs.find((ref) => ref.jobId === selectedJobId) ?? null
}

/** 校验返回结果确实属于所选 Job；不匹配时禁止按该 Job 展示 */
export function resultMatchesJob(
  result: Pick<ExtractResultResponse, 'job_id'> | null | undefined,
  jobId: string | null | undefined,
): boolean {
  return !!result && !!jobId && result.job_id === jobId
}

/** 仅保留可用的配置（排除已归档） */
export function selectableConfigurations(configs: ExtractConfiguration[]): ExtractConfiguration[] {
  return configs.filter((config) => config.status !== 'archived')
}

export type ConfigurationDefinitionPreview =
  | { kind: 'schema'; schema: unknown }
  | { kind: 'legacy'; fieldCount: number }
  | { kind: 'empty' }
  | { kind: 'published-template' }

/** 配置定义预览：schema > 旧版字段 > 无可预览定义 > 已发布模板（定义在执行时读取） */
export function configurationDefinitionPreview(
  config: Pick<ExtractConfiguration, 'draft_definition'> | null | undefined,
): ConfigurationDefinitionPreview {
  const definition = config?.draft_definition
  if (!definition) return { kind: 'published-template' }
  if (definition.data_schema !== undefined && definition.data_schema !== null) {
    return { kind: 'schema', schema: definition.data_schema }
  }
  const fieldCount = definition.fields?.length ?? 0
  if (fieldCount > 0) return { kind: 'legacy', fieldCount }
  return { kind: 'empty' }
}
