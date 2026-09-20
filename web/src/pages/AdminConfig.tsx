import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useProfileStore } from '@/store/useStore'
import { api } from '@/services/api'
import * as configurationsApi from '@/services/configurations'
import { readDraftingSessionId, writeDraftingSessionId } from '@/lib/draftingSession'
import type { Configuration, ConfigurationType } from '@/types'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Spinner } from '@/components/ui/spinner'
import { Settings, Sparkles, Plus, ChevronRight } from 'lucide-react'
import { formatDate } from '@/lib/utils'
import {
  CONFIGURATION_STATUS_LABELS,
  CONFIGURATION_TYPE_LABELS,
  IMPLEMENTED_CONFIGURATION_TYPES,
  configurationStatusVariant,
} from '@/lib/configuration'
import { AiTemplateWizard } from '@/components/admin/AiTemplateWizard'
import { ConfigurationDetail } from './AdminConfigurationDetail'

type View = 'list' | 'detail' | 'ai'

const CONFIGURATION_TYPES: ConfigurationType[] = [
  'extract',
  'classify',
  'split',
  'composite',
]

interface Tenant {
  id: string
  name: string
  code: string
}

export function AdminConfig() {
  const navigate = useNavigate()
  const { profile } = useProfileStore()
  const isSuperAdmin = profile?.role === 'super_admin'
  const isTenantAdmin = profile?.role === 'tenant_admin' || isSuperAdmin

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [selectedTenantId, setSelectedTenantId] = useState<string>('')
  const [searchParams, setSearchParams] = useSearchParams()
  // 草拟会话 id 存在 URL（`?session=`）：刷新页面后能回到同一个向导
  const draftingSessionId = readDraftingSessionId(searchParams.toString())
  const [view, setView] = useState<View>(draftingSessionId ? 'ai' : 'list')
  const [configurations, setConfigurations] = useState<Configuration[]>([])
  const [loadingList, setLoadingList] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [createForm, setCreateForm] = useState({
    name: '',
    code: '',
    description: '',
    type: 'extract' as ConfigurationType,
  })

  useEffect(() => {
    if (profile && !isTenantAdmin) {
      navigate('/', { replace: true })
    }
  }, [profile, isTenantAdmin, navigate])

  useEffect(() => {
    if (!isSuperAdmin) return
    api.get<Tenant[]>('/tenants').then(({ data }) => setTenants(data || []))
  }, [isSuperAdmin])

  useEffect(() => {
    if (!isSuperAdmin && profile?.tenant_id) {
      setSelectedTenantId(profile.tenant_id)
    }
  }, [isSuperAdmin, profile])

  const refreshList = useCallback(async () => {
    if (!selectedTenantId) return
    setLoadingList(true)
    try {
      const data = await configurationsApi.listConfigurations({ tenant_id: selectedTenantId })
      setConfigurations(data)
    } finally {
      setLoadingList(false)
    }
  }, [selectedTenantId])

  useEffect(() => {
    if (!draftingSessionId) {
      setView('list')
      setSelectedId(null)
    }
    void refreshList()
  }, [refreshList, draftingSessionId])

  const openDetail = (id: string) => {
    setSelectedId(id)
    setView('detail')
  }

  const openCreate = () => {
    setCreateForm({ name: '', code: '', description: '', type: 'extract' })
    setCreateError(null)
    setCreateOpen(true)
  }

  const handleCreate = async () => {
    if (!createForm.name.trim()) return
    setCreating(true)
    setCreateError(null)
    try {
      const created = await configurationsApi.createConfiguration({
        tenant_id: selectedTenantId,
        name: createForm.name.trim(),
        code: createForm.code.trim() || null,
        description: createForm.description.trim() || null,
        type: createForm.type,
      })
      setCreateOpen(false)
      await refreshList()
      openDetail(created.id)
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : '创建配置失败')
    } finally {
      setCreating(false)
    }
  }

  const handleWizardSessionChange = useCallback(
    (sessionId: string | null) => {
      setSearchParams(
        (prev) => new URLSearchParams(writeDraftingSessionId(prev.toString(), sessionId)),
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const handleWizardCommitted = async (configurationId?: string) => {
    handleWizardSessionChange(null)
    await refreshList()
    if (configurationId) {
      openDetail(configurationId)
    } else {
      setView('list')
    }
  }

  if (!profile) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Settings className="h-6 w-6 text-primary-400" />
        <div>
          <h1 className="text-xl font-semibold text-text-primary">系统配置</h1>
          <p className="text-sm text-text-muted">
            管理文档处理配置、识别字段与不可变修订
          </p>
        </div>
      </div>

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-4">
          {isSuperAdmin && (
            <div className="min-w-[200px]">
              <Label>选择部门</Label>
              <Select
                className="mt-1"
                value={selectedTenantId}
                onChange={(e) => setSelectedTenantId(e.target.value)}
              >
                <option value="">— 请选择部门 —</option>
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {!isSuperAdmin && profile?.tenant_name && (
            <div className="min-w-[160px]">
              <Label>所属部门</Label>
              <p className="mt-1 h-10 flex items-center px-3 rounded-lg border border-border-default bg-bg-secondary text-sm text-text-secondary">
                {profile.tenant_name}
              </p>
            </div>
          )}

          <div className="flex flex-1 justify-end gap-2">
            <Button
              variant="secondary"
              disabled={!selectedTenantId}
              onClick={() => setView('ai')}
            >
              <Sparkles className="h-4 w-4 mr-1" />
              AI 生成配置
            </Button>
            <Button disabled={!selectedTenantId} onClick={openCreate}>
              <Plus className="h-4 w-4 mr-1" />
              新建配置
            </Button>
          </div>
        </div>
      </Card>

      {!selectedTenantId ? (
        <div className="flex flex-col items-center justify-center py-24 text-text-muted">
          <Settings className="h-12 w-12 mb-4 opacity-20" />
          <p className="text-sm">请先选择部门</p>
        </div>
      ) : view === 'detail' && selectedId ? (
        <ConfigurationDetail
          configurationId={selectedId}
          onBack={() => {
            setView('list')
            setSelectedId(null)
          }}
          onChanged={refreshList}
        />
      ) : view === 'ai' ? (
        <div className="space-y-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              handleWizardSessionChange(null)
              setView('list')
            }}
          >
            ← 返回配置列表
          </Button>
          <Card className="p-6">
            <AiTemplateWizard
              tenantId={selectedTenantId}
              tenantName={tenants.find((tenant) => tenant.id === selectedTenantId)?.name}
              initialSessionId={draftingSessionId}
              onSessionChange={handleWizardSessionChange}
              onCommitted={handleWizardCommitted}
            />
          </Card>
        </div>
      ) : (
        <Card className="p-6">
          {loadingList ? (
            <div className="flex items-center justify-center py-16">
              <Spinner />
            </div>
          ) : configurations.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-text-muted">
              <Settings className="h-10 w-10 mb-4 opacity-20" />
              <p className="text-sm">暂无配置，点击"新建配置"或使用"AI 生成配置"</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-border-default">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-default bg-bg-secondary text-text-muted">
                    <th className="px-4 py-2.5 text-left font-medium">名称</th>
                    <th className="px-4 py-2.5 text-left font-medium">类型</th>
                    <th className="px-4 py-2.5 text-left font-medium">状态</th>
                    <th className="px-4 py-2.5 text-left font-medium">字段</th>
                    <th className="px-4 py-2.5 text-left font-medium">更新于</th>
                    <th className="px-4 py-2.5 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {configurations.map((configuration) => (
                    <tr
                      key={configuration.id}
                      className="border-b border-border-default last:border-0 hover:bg-bg-hover transition-colors cursor-pointer"
                      onClick={() => openDetail(configuration.id)}
                    >
                      <td className="px-4 py-3">
                        <p className="font-medium text-text-primary">{configuration.name}</p>
                        {configuration.code && (
                          <p className="mt-0.5 font-mono text-xs text-text-muted">
                            {configuration.code}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-text-secondary">
                        {CONFIGURATION_TYPE_LABELS[configuration.type] ?? configuration.type}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={configurationStatusVariant(configuration.status)}>
                          {CONFIGURATION_STATUS_LABELS[configuration.status]}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-text-secondary">
                        {configuration.draft_definition?.fields?.length ?? 0}
                      </td>
                      <td className="px-4 py-3 text-text-muted text-xs">
                        {formatDate(configuration.updated_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <ChevronRight className="inline h-4 w-4 text-text-muted" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Modal
        open={createOpen}
        title="新建配置"
        onClose={() => setCreateOpen(false)}
        onConfirm={handleCreate}
        confirmText={creating ? '创建中...' : '创建'}
      >
        <div className="mt-4 space-y-3">
          <div>
            <Label>配置名称 *</Label>
            <Input
              className="mt-1"
              value={createForm.name}
              onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. 检测报告提取"
            />
          </div>
          <div>
            <Label>配置 code</Label>
            <Input
              className="mt-1 font-mono"
              value={createForm.code}
              onChange={(e) => setCreateForm((f) => ({ ...f, code: e.target.value }))}
              placeholder="e.g. inspection_report"
            />
          </div>
          <div>
            <Label>类型</Label>
            <Select
              className="mt-1"
              value={createForm.type}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, type: e.target.value as ConfigurationType }))
              }
            >
              {CONFIGURATION_TYPES.map((type) => {
                const implemented = IMPLEMENTED_CONFIGURATION_TYPES.includes(type)
                return (
                  <option key={type} value={type} disabled={!implemented}>
                    {CONFIGURATION_TYPE_LABELS[type]}
                    {implemented ? '' : '（未实现）'}
                  </option>
                )
              })}
            </Select>
          </div>
          <div>
            <Label>描述</Label>
            <Textarea
              className="mt-1"
              value={createForm.description}
              onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          {createError && <p className="text-sm text-error-500">{createError}</p>}
        </div>
      </Modal>
    </div>
  )
}
