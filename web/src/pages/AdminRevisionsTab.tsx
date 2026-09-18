import type { ConfigurationRevision } from '@/types'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { History } from 'lucide-react'
import { formatDate } from '@/lib/utils'

export function RevisionsTab({
  revisions,
  currentRevisionId,
  loading,
}: {
  revisions: ConfigurationRevision[]
  currentRevisionId: string | null
  loading: boolean
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    )
  }

  if (revisions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-text-muted">
        <History className="h-10 w-10 mb-3 opacity-30" />
        <p className="text-sm">尚未发布，暂无修订历史</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {revisions.map((revision) => {
        const definition = revision.definition
        const isCurrent = revision.id === currentRevisionId
        return (
          <Card key={revision.id} className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-text-primary">
                  修订 #{revision.revision_number}
                </span>
                {isCurrent && <Badge variant="success">当前版本</Badge>}
              </div>
              <span className="text-xs text-text-muted">
                {formatDate(revision.published_at ?? revision.created_at)}
              </span>
            </div>
            <p className="mt-2 text-xs text-text-muted">
              {definition?.fields?.length ?? 0} 个字段
              {definition?.extraction_prompt ? ' · 含提取 Prompt' : ''}
            </p>
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-primary-400 hover:text-primary-300">
                查看完整定义
              </summary>
              <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-bg-secondary p-3 text-xs text-text-secondary whitespace-pre-wrap break-words">
                {JSON.stringify(definition ?? {}, null, 2)}
              </pre>
            </details>
          </Card>
        )
      })}
    </div>
  )
}
