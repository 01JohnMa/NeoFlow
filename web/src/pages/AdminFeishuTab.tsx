import { useState, useEffect } from 'react'
import * as adminApi from '@/services/admin'
import type { AdminTemplate } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { ToggleLeft, ToggleRight, Save } from 'lucide-react'

export function FeishuConfigTab({
  template,
  onSaved,
}: {
  template: AdminTemplate
  onSaved: (updated: AdminTemplate) => void
}) {
  const [token, setToken] = useState(template.feishu_bitable_token ?? '')
  const [tableId, setTableId] = useState(template.feishu_table_id ?? '')
  const [autoApprove, setAutoApprove] = useState(template.auto_approve)
  const [pushAttachment, setPushAttachment] = useState(template.push_attachment ?? true)
  const [perPageExtraction, setPerPageExtraction] = useState(template.per_page_extraction ?? false)
  const [extractionMode, setExtractionMode] = useState<'ocr_llm' | 'vlm'>(template.extraction_mode ?? 'ocr_llm')
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    setToken(template.feishu_bitable_token ?? '')
    setTableId(template.feishu_table_id ?? '')
    setAutoApprove(template.auto_approve)
    setPushAttachment(template.push_attachment ?? true)
    setPerPageExtraction(template.per_page_extraction ?? false)
    setExtractionMode(template.extraction_mode ?? 'ocr_llm')
  }, [template])

  const handleSave = async () => {
    setSaving(true)
    setSuccess(false)
    try {
      const updated = await adminApi.updateTemplateConfig(template.id, {
        feishu_bitable_token: token,
        feishu_table_id: tableId,
        auto_approve: autoApprove,
        push_attachment: pushAttachment,
        per_page_extraction: perPageExtraction,
        extraction_mode: extractionMode,
      })
      onSaved({ ...template, ...updated })
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
        {/* ── 处理模式选择 ── */}
        <div>
          <Label>文档处理模式</Label>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setExtractionMode('ocr_llm')}
              className={`rounded-lg border p-4 text-left transition-all ${
                extractionMode === 'ocr_llm'
                  ? 'border-primary-400 bg-primary-400/10 ring-1 ring-primary-400'
                  : 'border-border-default bg-bg-secondary hover:border-border-hover'
              }`}
            >
              <p className="text-sm font-medium text-text-primary">OCR + LLM</p>
              <p className="mt-1 text-xs text-text-muted">印刷体文档，速度快、成本低</p>
            </button>
            <button
              type="button"
              onClick={() => setExtractionMode('vlm')}
              className={`rounded-lg border p-4 text-left transition-all ${
                extractionMode === 'vlm'
                  ? 'border-primary-400 bg-primary-400/10 ring-1 ring-primary-400'
                  : 'border-border-default bg-bg-secondary hover:border-border-hover'
              }`}
            >
              <p className="text-sm font-medium text-text-primary">多模态 VLM</p>
              <p className="mt-1 text-xs text-text-muted">手写/复杂版式，识别更准</p>
            </button>
          </div>
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
      </div>
      <Button onClick={handleSave} disabled={saving}>
        {saving ? <Spinner size="sm" className="mr-2" /> : <Save className="h-4 w-4 mr-2" />}
        {success ? '已保存' : '保存配置'}
      </Button>
    </div>
  )
}
