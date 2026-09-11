import { useQuery } from '@tanstack/react-query'
import * as jobsService from '@/services/jobs'

export const jobKeys = {
  all: ['jobs'] as const,
  detail: (jobId: string) => [...jobKeys.all, 'detail', jobId] as const,
  parseResult: (jobId: string) => [...jobKeys.all, 'parse-result', jobId] as const,
}

// Job 状态：未完成时每 2 秒轮询，完成后停止
export function useJob(jobId?: string) {
  return useQuery({
    queryKey: jobKeys.detail(jobId ?? ''),
    queryFn: () => jobsService.getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'completed' || status === 'failed' ? false : 2000
    },
  })
}

// ParseResult：仅在 Job 完成后拉取
export function useParseResult(jobId?: string, enabled: boolean = true) {
  return useQuery({
    queryKey: jobKeys.parseResult(jobId ?? ''),
    queryFn: () => jobsService.getParseResult(jobId!),
    enabled: !!jobId && enabled,
  })
}
