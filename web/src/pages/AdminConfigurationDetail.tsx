import { useCallback, useEffect, useState } from 'react'
import * as configurationsApi from '@/services/configurations'
import type { Configuration, ConfigurationRevision } from '@/types'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Modal } from '@/components/ui/modal'
import { Spinner } from '@/components/ui/spinner'
import {
  ArrowLeft,
  Archive,
  Rocket,
} from 'lucide-react'
import { cn, formatDate } from '@/lib/utils'
import {
  CONFIGURATION_STATUS_LABELS,
  CONFIGURATION_TYPE_LABELS,
  configurationStatusVariant,
} from '@/lib/configuration'
import { FieldsTab } from './AdminFieldsTab'
import { RevisionsTab } from './AdminRevisionsTab'

type Tab = 'fields' | 'revisions'

export function ConfigurationDetail({
  configurationId,
  onBack,
  onChanged,
}: {
  configurationId: string
  onBack: () => void
  onChanged: () => void
}) {
  const [configuration, setConfiguration] = useState<Configuration | null>(null)
  const [revisions, setRevisions] = useState<ConfigurationRevision[]>([])
  const [loading, setLoading] = useState(true)
  const [revisionsLoading, setRevisionsLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('fields')
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editorDirty, setEditorDirty] = useState(false)

  const loadRevisions = useCallback(async () => {
    setRevisionsLoading(true)
    try {
      setRevisions(await configurationsApi.listRevisions(configurationId))
    } finally {
      setRevisionsLoading(false)
    }
  }, [configurationId])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [detail] = await Promise.all([
        configurationsApi.getConfiguration(configurationId),
        loadRevisions(),
      ])
      setConfiguration(detail)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载配置失败')
    } finally {
      setLoading(false)
    }
  }, [configurationId, loadRevisions])

  useEffect(() => {
    load()
  }, [load])

  const handleUpdated = useCallback(
    (updated: Configuration) => {
      setConfiguration((prev) => ({
        ...updated,
        current_revision: updated.current_revision ?? prev?.current_revision ?? null,
      }))
      void loadRevisions()
      onChanged()
    },
    [loadRevisions, onChanged],
  )

  const handlePublish = async () => {
    if (editorDirty) { setError('请先保存字段草稿，再发布。'); return }
    setActionLoading('publish')
    setError(null)
    try {
      await configurationsApi.publishConfiguration(configurationId)
      await load()
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : '发布失败')
    } finally {
      setActionLoading(null)
    }
  }

  const handleArchive = async () => {
    setActionLoading('archive')
    setError(null)
    try {
      const updated = await configurationsApi.archiveConfiguration(configurationId)
      setConfiguration((prev) => ({ ...updated, current_revision: prev?.current_revision ?? null }))
      setConfirmArchive(false)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : '归档失败')
    } finally {
      setActionLoading(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner />
      </div>
    )
  }

  if (!configuration) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => { if (!editorDirty || window.confirm('字段草稿尚未保存，确定离开？')) onBack() }}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          返回配置列表
        </Button>
        <p className="text-sm text-error-500">{error ?? '配置不存在'}</p>
      </div>
    )
  }

  const definition = configuration.draft_definition
  const fieldsCount = configuration.type === 'extract'
    ? Object.keys(definition?.data_schema?.properties ?? {}).length
    : definition?.fields?.length ?? 0
  const hasUnpublishedChanges =
    configuration.status === 'draft' && Boolean(configuration.current_revision_id)

  const tabs: { key: Tab; label: string }[] = [
    { key: 'fields', label: `识别字段 (${fieldsCount})` },
    { key: 'revisions', label: `修订历史 (${revisions.length})` },
  ]

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon-sm" onClick={() => { if (!editorDirty || window.confirm('字段草稿尚未保存，确定离开？')) onBack() }} title="返回配置列表">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-text-primary">{configuration.name}</h2>
              <Badge variant={configurationStatusVariant(configuration.status)}>
                {CONFIGURATION_STATUS_LABELS[configuration.status]}
              </Badge>
              <Badge variant="outline">
                {CONFIGURATION_TYPE_LABELS[configuration.type] ?? configuration.type}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-text-muted">
              {configuration.code ? <span className="font-mono mr-3">{configuration.code}</span> : null}
              更新于 {formatDate(configuration.updated_at)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {configuration.status !== 'archived' && (
            <Button
              size="sm"
              variant="secondary"
              disabled={actionLoading !== null || editorDirty}
              onClick={() => setConfirmArchive(true)}
            >
              <Archive className="h-4 w-4 mr-1" />
              归档
            </Button>
          )}
          {configuration.status === 'draft' && (
            <Button
              size="sm"
              disabled={actionLoading !== null || editorDirty}
              loading={actionLoading === 'publish'}
              onClick={handlePublish}
            >
              <Rocket className="h-4 w-4 mr-1" />
              发布
            </Button>
          )}
        </div>
      </div>

      {configuration.description && (
        <p className="text-sm text-text-secondary">{configuration.description}</p>
      )}

      {hasUnpublishedChanges && (
        <div className="rounded-lg border border-warning-500/30 bg-warning-500/10 px-4 py-3 text-sm text-warning-400">
          当前配置已有未发布的修改，发布后将生成新的不可变修订。
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-error-500/30 bg-error-500/10 px-4 py-3 text-sm text-error-500">
          {error}
        </div>
      )}

      <Card className="p-6">
        <div className="mb-5 flex flex-wrap gap-1 rounded-xl border border-border-default bg-bg-secondary p-1 w-fit">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => { if (tab.key === activeTab) return; if (!editorDirty || window.confirm('字段草稿尚未保存，确定切换？')) { setEditorDirty(false); setActiveTab(tab.key) } }}
              className={cn(
                'rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200',
                activeTab === tab.key
                  ? 'bg-primary-500/10 text-primary-400 border border-primary-500/20'
                  : 'text-text-secondary hover:text-text-primary',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {configuration.status === 'archived' && activeTab !== 'revisions' && (
          <div className="mb-4 rounded-lg border border-border-default bg-bg-secondary px-4 py-3 text-sm text-text-muted">
            配置已归档，不可再修改。
          </div>
        )}

        {activeTab === 'fields' && (
          <FieldsTab configuration={configuration} onUpdated={handleUpdated} onDirtyChange={setEditorDirty} />
        )}
        {activeTab === 'revisions' && (
          <RevisionsTab
            revisions={revisions}
            currentRevisionId={configuration.current_revision_id}
            loading={revisionsLoading}
          />
        )}
      </Card>

      <Modal
        open={confirmArchive}
        title="归档配置"
        message={`确定归档配置「${configuration.name}」？归档后不可修改或发布，已生成的修订保留。`}
        confirmText={actionLoading === 'archive' ? '归档中...' : '归档'}
        cancelText="取消"
        onClose={() => setConfirmArchive(false)}
        onConfirm={handleArchive}
      />
    </div>
  )
}
