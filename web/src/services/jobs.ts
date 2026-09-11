import { api } from './api'
import type { ParseResult, ParseResultResponse, ProcessingJob } from '@/types'

export async function getJob(jobId: string): Promise<ProcessingJob> {
  const { data } = await api.get<ProcessingJob>(`/jobs/${jobId}`)
  return data
}

export async function getParseResult(jobId: string): Promise<ParseResult> {
  const { data } = await api.get<ParseResultResponse>(`/jobs/${jobId}/parse-result`)
  return data.data
}
