import { useState, useEffect } from 'react'
import * as configurationsApi from '@/services/configurations'
import type { Configuration } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { ToggleLeft, ToggleRight, Save } from 'lucide-react'

export function FeishuConfigTab({
  configuration,
  onUpdated,
}: {
  configuration: Configuration
  onUpdated: (configuration: Configuration) => void
}) {
  const definition = configuration.draft_definition
  const [token, setToken] = useState(definition?.feishu?.bitable_token ?? '')
  const [tableId, setTableId] = useState(definition?.feishu?.table_id ?? '')
  const [autoApprove, setAutoApprove] = useState(definition?.auto_approve ?? false)
  const [pushAttachment, setPushAttachment] = useState(definition?.push_attachment ?? true)
  const [perPageExtraction, setPerPageExtraction] = useState(definition?.per_page_extraction ?? false)
  const [parseMode, setParseMode] = useState<'pipeline' | 'vlm'>(
    definition?.parse?.model_version === 'vlm' ? 'vlm' : 'pipeline',
  )
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    setToken(definition?.feishu?.bitable_token ?? '')
    setTableId(definition?.feishu?.table_id ?? '')
    setAutoApprove(definition?.auto_approve ?? false)
    setPushAttachment(definition?.push_attachment ?? true)
    setPerPageExtraction(definition?.per_page_extraction ?? false)
    setParseMode(definition?.parse?.model_version === 'vlm' ? 'vlm' : 'pipeline')
  }, [definition])

  const handleSave = async () => {
    setSaving(true)
    setSuccess(false)
    try {
      const updated = await configurationsApi.updateConfiguration(configuration.id, {
        definition: {
          feishu: { bitable_token: token, table_id: tableId },
          auto_approve: autoApprove,
          push_attachment: pushAttachment,
          per_page_extraction: perPageExtraction,
          parse: { ...(definition?.parse ?? {}), model_version: parseMode },
        },
      })
      onUpdated(updated)
      setSuccess(true)
      setTimeout(() => setSuccess(false), 2000)
    } catch (e) {
      console.error('保存飞书配置失败', e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div className="space-y-4">
        {/* ── 解析模式选择 ── */}
        <div>
          <Label>解析模式</Label>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setParseMode('pipeline')}
              className={`rounded-lg border p-4 text-left transition-all ${
                parseMode === 'pipeline'
                  ? 'border-primary-400 bg-primary-400/10 ring-1 ring-primary-400'
                  : 'border-border-default bg-bg-secondary hover:border-border-hover'
              }`}
            >
              <p className="text-sm font-medium text-text-primary">快速解析</p>
              <p className="mt-1 text-xs text-text-muted">标准印刷体，速度快、成本低</p>
            </button>
            <button
              type="button"
              onClick={() => setParseMode('vlm')}
              className={`rounded-lg border p-4 text-left transition-all ${
                parseMode === 'vlm'
                  ? 'border-primary-400 bg-primary-400/10 ring-1 ring-primary-400'
                  : 'border-border-default bg-bg-secondary hover:border-border-hover'
              }`}
            >
              <p className="text-sm font-medium text-text-primary">高精度解析</p>
              <p className="mt-1 text-xs text-text-muted">复杂版式/手写，识别更准、稍慢</p>
            </button>
          </div>
          <p className="mt-2 text-xs text-text-muted">解析由 MinerU 执行，提取基于解析结果</p>
        </div>

        {/* ── 飞书配置 ── */}
        <div>
          <Label>Bitable App Token</Label>
          <Input
            className="mt-1"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="feishu_bitable_token"
          />
          <p className="mt-1 text-xs text-text-muted">飞书多维表格的 App Token，从多维表格 URL 中获取</p>
        </div>
        <div>
          <Label>Table ID</Label>
          <Input
            className="mt-1"
            value={tableId}
            onChange={(e) => setTableId(e.target.value)}
            placeholder="feishu_table_id"
          />
          <p className="mt-1 text-xs text-text-muted">具体数据表的 Table ID</p>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-border-default bg-bg-secondary p-4">
          <div>
            <p className="text-sm font-medium text-text-primary">自动审核</p>
            <p className="text-xs text-text-muted">开启后文档识别完成将自动推送飞书，无需人工确认</p>
          </div>
          <button
            type="button"
            onClick={() => setAutoApprove((v) => !v)}
            className="text-primary-400 hover:text-primary-300 transition-colors"
          >
            {autoApprove ? (
              <ToggleRight className="h-8 w-8" />
            ) : (
              <ToggleLeft className="h-8 w-8 text-text-muted" />
            )}
          </button>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-border-default bg-bg-secondary p-4">
          <div>
            <p className="text-sm font-medium text-text-primary">推送附件</p>
            <p className="text-xs text-text-muted">开启后推送飞书时同步上传原始文件作为附件</p>
          </div>
          <button
            type="button"
            onClick={() => setPushAttachment((v) => !v)}
            className="text-primary-400 hover:text-primary-300 transition-colors"
          >
            {pushAttachment ? (
              <ToggleRight className="h-8 w-8" />
            ) : (
              <ToggleLeft className="h-8 w-8 text-text-muted" />
            )}
          </button>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-border-default bg-bg-secondary p-4">
          <div>
            <p className="text-sm font-medium text-text-primary">逐页提取</p>
            <p className="text-xs text-text-muted">开启后将按页独立识别，每页产生一个样品结果（适用于每页一个样品的报告）</p>
          </div>
          <button
            type="button"
            onClick={() => setPerPageExtraction((v) => !v)}
            className="text-primary-400 hover:text-primary-300 transition-colors"
          >
            {perPageExtraction ? (
              <ToggleRight className="h-8 w-8" />
            ) : (
              <ToggleLeft className="h-8 w-8 text-text-muted" />
            )}
          </button>
        </div>
        {definition?.excel?.file_name && (
          <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
            <p className="text-sm font-medium text-text-primary">Excel 输出模板</p>
            <p className="mt-1 text-xs text-text-muted">
              {definition.excel.file_name}（{definition.excel.placeholders.length} 个槽位）
            </p>
          </div>
        )}
      </div>
      <Button onClick={handleSave} disabled={saving || configuration.status === 'archived'}>
        {saving ? <Spinner size="sm" className="mr-2" /> : <Save className="h-4 w-4 mr-2" />}
        {success ? '已保存' : '保存配置'}
      </Button>
    </div>
  )
}
