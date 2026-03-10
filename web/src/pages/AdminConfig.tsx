import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProfileStore } from '@/store/useStore'
import { api } from '@/services/api'
import * as adminApi from '@/services/admin'
import type {
  AdminTemplate,
  TemplateField,
  TemplateExample,
  CreateFieldPayload,
  CreateExamplePayload,
} from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Modal } from '@/components/ui/modal'
import { Card } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import {
  Settings,
  Plus,
  Pencil,
  Trash2,
  GripVertical,
  ToggleLeft,
  ToggleRight,
  Save,
  ChevronUp,
  ChevronDown,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ============ 辅助类型 ============

type Tab = 'feishu' | 'fields' | 'examples'

interface Tenant {
  id: string
  name: string
  code: string
}

// ============ JSON 编辑器组件 ============

function JsonTextarea({
  value,
  onChange,
  placeholder,
  rows = 6,
}: {
  value: string
  onChange: (v: string, valid: boolean) => void
  placeholder?: string
  rows?: number
}) {
  const [error, setError] = useState('')

  const handleChange = (v: string) => {
    try {
      if (v.trim()) JSON.parse(v)
      setError('')
      onChange(v, true)
    } catch {
      setError('JSON 格式有误')
      onChange(v, false)
    }
  }

  return (
    <div>
      <Textarea
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className="font-mono text-xs"
      />
      {error && <p className="mt-1 text-xs text-error-500">{error}</p>}
    </div>
  )
}

// ============ Tab 1：飞书多维表格配置 ============

function FeishuConfigTab({
  template,
  onSaved,
}: {
  template: AdminTemplate
  onSaved: (updated: AdminTemplate) => void
}) {
  const [token, setToken] = useState(template.feishu_bitable_token ?? '')
  const [tableId, setTableId] = useState(template.feishu_table_id ?? '')
  const [autoApprove, setAutoApprove] = useState(template.auto_approve)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    setToken(template.feishu_bitable_token ?? '')
    setTableId(template.feishu_table_id ?? '')
    setAutoApprove(template.auto_approve)
  }, [template])

  const handleSave = async () => {
    setSaving(true)
    setSuccess(false)
    try {
      const updated = await adminApi.updateTemplateConfig(template.id, {
        feishu_bitable_token: token,
        feishu_table_id: tableId,
        auto_approve: autoApprove,
      })
      // 后端若返回不完整对象时，保留当前模板字段避免 UI 被空对象覆盖
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
      </div>
      <Button onClick={handleSave} disabled={saving}>
        {saving ? <Spinner size="sm" className="mr-2" /> : <Save className="h-4 w-4 mr-2" />}
        {success ? '已保存' : '保存配置'}
      </Button>
    </div>
  )
}

// ============ 字段弹窗表单 ============

const EMPTY_FIELD: CreateFieldPayload = {
  field_key: '',
  field_label: '',
  field_type: 'text',
  extraction_hint: '',
  feishu_column: '',
  sort_order: 0,
  review_enforced: false,
  review_allowed_values: null,
}

function FieldFormModal({
  open,
  initial,
  onClose,
  onSubmit,
}: {
  open: boolean
  initial?: Partial<CreateFieldPayload> & { id?: string }
  onClose: () => void
  onSubmit: (data: CreateFieldPayload) => Promise<void>
}) {
  const [form, setForm] = useState<CreateFieldPayload>({ ...EMPTY_FIELD, ...initial })
  const [allowedInput, setAllowedInput] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setForm({ ...EMPTY_FIELD, ...initial })
    setAllowedInput('')
  }, [initial, open])

  const allowedValues = form.review_allowed_values ?? []

  const addAllowedValue = () => {
    const v = allowedInput.trim()
    if (v && !allowedValues.includes(v)) {
      setForm((f) => ({ ...f, review_allowed_values: [...allowedValues, v] }))
      setAllowedInput('')
    }
  }

  const removeAllowedValue = (v: string) => {
    setForm((f) => ({
      ...f,
      review_allowed_values: allowedValues.filter((x) => x !== v),
    }))
  }

  const handleSubmit = async () => {
    if (!form.field_key || !form.field_label) return
    setSubmitting(true)
    try {
      await onSubmit(form)
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title={initial?.id ? '编辑字段' : '新增字段'}
      onClose={onClose}
      onConfirm={handleSubmit}
      confirmText={submitting ? '保存中...' : '保存'}
    >
      <div className="mt-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>字段键名 *</Label>
            <Input
              className="mt-1"
              value={form.field_key}
              onChange={(e) => setForm((f) => ({ ...f, field_key: e.target.value }))}
              placeholder="e.g. sample_name"
              disabled={!!initial?.id}
            />
          </div>
          <div>
            <Label>字段标签 *</Label>
            <Input
              className="mt-1"
              value={form.field_label}
              onChange={(e) => setForm((f) => ({ ...f, field_label: e.target.value }))}
              placeholder="e.g. 样品名称"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>字段类型</Label>
            <Select
              className="mt-1"
              value={form.field_type}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  field_type: e.target.value as 'text' | 'date' | 'number',
                }))
              }
            >
              <option value="text">文本</option>
              <option value="date">日期</option>
              <option value="number">数值</option>
            </Select>
          </div>
          <div>
            <Label>飞书列名</Label>
            <Input
              className="mt-1"
              value={form.feishu_column ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, feishu_column: e.target.value }))}
              placeholder="飞书多维表格列标题"
            />
          </div>
        </div>
        <div>
          <Label>提取提示（Prompt Hint）</Label>
          <Input
            className="mt-1"
            value={form.extraction_hint ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, extraction_hint: e.target.value }))}
            placeholder="给 LLM 的额外提取说明"
          />
        </div>
        <div>
          <Label>排序序号</Label>
          <Input
            className="mt-1"
            type="number"
            value={form.sort_order}
            onChange={(e) => setForm((f) => ({ ...f, sort_order: Number(e.target.value) }))}
          />
        </div>
        <div className="rounded-lg border border-border-default p-3 space-y-2">
          <div className="flex items-center justify-between">
            <Label>需要人工审核</Label>
            <button
              type="button"
              onClick={() => setForm((f) => ({ ...f, review_enforced: !f.review_enforced }))}
              className="text-primary-400"
            >
              {form.review_enforced ? (
                <ToggleRight className="h-6 w-6" />
              ) : (
                <ToggleLeft className="h-6 w-6 text-text-muted" />
              )}
            </button>
          </div>
          {form.review_enforced && (
            <div>
              <Label className="text-xs text-text-muted">允许的审核值（枚举，留空则不限制）</Label>
              <div className="mt-1 flex gap-2">
                <Input
                  value={allowedInput}
                  onChange={(e) => setAllowedInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addAllowedValue()}
                  placeholder="输入后按 Enter 添加"
                  className="text-xs"
                />
                <Button type="button" variant="outline" size="sm" onClick={addAllowedValue}>
                  添加
                </Button>
              </div>
              {allowedValues.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {allowedValues.map((v) => (
                    <span
                      key={v}
                      className="flex items-center gap-1 rounded bg-primary-500/10 px-2 py-0.5 text-xs text-primary-400"
                    >
                      {v}
                      <button
                        type="button"
                        onClick={() => removeAllowedValue(v)}
                        className="hover:text-error-400"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}

// ============ Tab 2：识别字段管理 ============

function FieldsTab({ templateId }: { templateId: string }) {
  const [fields, setFields] = useState<TemplateField[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<TemplateField | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<TemplateField | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await adminApi.fetchFields(templateId)
      setFields(data)
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => {
    load()
  }, [load])

  const handleCreate = async (payload: CreateFieldPayload) => {
    await adminApi.createField(templateId, payload)
    await load()
  }

  const handleUpdate = async (payload: CreateFieldPayload) => {
    if (!editTarget) return
    await adminApi.updateField(editTarget.id, payload)
    await load()
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await adminApi.deleteField(deleteTarget.id)
      setDeleteTarget(null)
      await load()
    } finally {
      setDeleting(false)
    }
  }

  const moveField = async (index: number, direction: 'up' | 'down') => {
    const newFields = [...fields]
    const swapIndex = direction === 'up' ? index - 1 : index + 1
    if (swapIndex < 0 || swapIndex >= newFields.length) return
    ;[newFields[index], newFields[swapIndex]] = [newFields[swapIndex], newFields[index]]
    const reordered = newFields.map((f, i) => ({ ...f, sort_order: i }))
    setFields(reordered)
    await adminApi.reorderFields(
      templateId,
      reordered.map((f) => ({ id: f.id, sort_order: f.sort_order })),
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-muted">共 {fields.length} 个字段</p>
        <Button
          size="sm"
          onClick={() => {
            setEditTarget(null)
            setModalOpen(true)
          }}
        >
          <Plus className="h-4 w-4 mr-1" />
          新增字段
        </Button>
      </div>

      {fields.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-text-muted">
          <Settings className="h-10 w-10 mb-3 opacity-30" />
          <p className="text-sm">暂无字段，点击"新增字段"开始配置</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border-default">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-default bg-bg-secondary text-text-muted">
                <th className="px-3 py-2 text-left font-medium w-8">#</th>
                <th className="px-3 py-2 text-left font-medium">键名</th>
                <th className="px-3 py-2 text-left font-medium">标签</th>
                <th className="px-3 py-2 text-left font-medium">类型</th>
                <th className="px-3 py-2 text-left font-medium">飞书列</th>
                <th className="px-3 py-2 text-left font-medium">提取提示</th>
                <th className="px-3 py-2 text-center font-medium">审核</th>
                <th className="px-3 py-2 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field, idx) => (
                <tr
                  key={field.id}
                  className="border-b border-border-default last:border-0 hover:bg-bg-hover transition-colors"
                >
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-0.5">
                      <button
                        onClick={() => moveField(idx, 'up')}
                        disabled={idx === 0}
                        className="text-text-muted hover:text-text-primary disabled:opacity-20"
                      >
                        <ChevronUp className="h-3 w-3" />
                      </button>
                      <button
                        onClick={() => moveField(idx, 'down')}
                        disabled={idx === fields.length - 1}
                        className="text-text-muted hover:text-text-primary disabled:opacity-20"
                      >
                        <ChevronDown className="h-3 w-3" />
                      </button>
                    </div>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-primary-400">{field.field_key}</td>
                  <td className="px-3 py-2 text-text-primary">{field.field_label}</td>
                  <td className="px-3 py-2 text-text-secondary">
                    {{ text: '文本', date: '日期', number: '数值' }[field.field_type] ?? field.field_type}
                  </td>
                  <td className="px-3 py-2 text-text-secondary text-xs">{field.feishu_column || '-'}</td>
                  <td className="px-3 py-2 text-text-muted text-xs max-w-[160px] truncate">
                    {field.extraction_hint || '-'}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {field.review_enforced ? (
                      <span className="inline-block rounded-full bg-warning-500/15 px-2 py-0.5 text-xs text-warning-400">
                        必填
                      </span>
                    ) : (
                      <span className="text-text-muted text-xs">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => {
                          setEditTarget(field)
                          setModalOpen(true)
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="hover:text-error-500"
                        onClick={() => setDeleteTarget(field)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <FieldFormModal
        open={modalOpen}
        initial={
          editTarget
            ? {
                ...editTarget,
                extraction_hint: editTarget.extraction_hint ?? undefined,
                feishu_column: editTarget.feishu_column ?? undefined,
                review_allowed_values: editTarget.review_allowed_values ?? undefined,
              }
            : undefined
        }
        onClose={() => setModalOpen(false)}
        onSubmit={editTarget ? handleUpdate : handleCreate}
      />

      <Modal
        open={!!deleteTarget}
        title="删除字段"
        message={`确定删除字段「${deleteTarget?.field_label}」？此操作不可恢复。`}
        confirmText={deleting ? '删除中...' : '删除'}
        cancelText="取消"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </div>
  )
}

// ============ Tab 3：Few-shot 示例管理 ============

const EMPTY_EXAMPLE: CreateExamplePayload = {
  example_input: '',
  example_output: {},
  sort_order: 0,
  is_active: true,
}

function ExampleFormModal({
  open,
  initial,
  onClose,
  onSubmit,
}: {
  open: boolean
  initial?: Partial<CreateExamplePayload> & { id?: string }
  onClose: () => void
  onSubmit: (data: CreateExamplePayload) => Promise<void>
}) {
  const [form, setForm] = useState<CreateExamplePayload>({ ...EMPTY_EXAMPLE, ...initial })
  const [outputStr, setOutputStr] = useState(
    initial?.example_output ? JSON.stringify(initial.example_output, null, 2) : '{}',
  )
  const [outputValid, setOutputValid] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setForm({ ...EMPTY_EXAMPLE, ...initial })
    setOutputStr(
      initial?.example_output ? JSON.stringify(initial.example_output, null, 2) : '{}',
    )
    setOutputValid(true)
  }, [initial, open])

  const handleSubmit = async () => {
    if (!outputValid) return
    setSubmitting(true)
    try {
      let parsed: Record<string, unknown> = {}
      try {
        parsed = JSON.parse(outputStr)
      } catch {
        return
      }
      await onSubmit({ ...form, example_output: parsed })
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title={initial?.id ? '编辑示例' : '新增示例'}
      onClose={onClose}
      onConfirm={handleSubmit}
      confirmText={submitting ? '保存中...' : '保存'}
    >
      <div className="mt-4 space-y-3">
        <div>
          <Label>输入文本（OCR 原文片段）</Label>
          <Textarea
            className="mt-1 font-mono text-xs"
            rows={5}
            value={form.example_input}
            onChange={(e) => setForm((f) => ({ ...f, example_input: e.target.value }))}
            placeholder="粘贴一段真实 OCR 识别文本..."
          />
        </div>
        <div>
          <Label>期望输出（JSON）</Label>
          <JsonTextarea
            value={outputStr}
            onChange={(v, valid) => {
              setOutputStr(v)
              setOutputValid(valid)
            }}
            placeholder='{ "field_key": "value" }'
            rows={5}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>排序序号</Label>
            <Input
              className="mt-1"
              type="number"
              value={form.sort_order}
              onChange={(e) => setForm((f) => ({ ...f, sort_order: Number(e.target.value) }))}
            />
          </div>
          <div className="flex items-end pb-0.5">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, is_active: !f.is_active }))}
                className="text-primary-400"
              >
                {form.is_active ? (
                  <ToggleRight className="h-6 w-6" />
                ) : (
                  <ToggleLeft className="h-6 w-6 text-text-muted" />
                )}
              </button>
              <Label className="cursor-pointer" onClick={() => setForm((f) => ({ ...f, is_active: !f.is_active }))}>
                启用
              </Label>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}

function ExamplesTab({ templateId }: { templateId: string }) {
  const [examples, setExamples] = useState<TemplateExample[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<TemplateExample | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<TemplateExample | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await adminApi.fetchExamples(templateId)
      setExamples(data)
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => {
    load()
  }, [load])

  const handleCreate = async (payload: CreateExamplePayload) => {
    await adminApi.createExample(templateId, payload)
    await load()
  }

  const handleUpdate = async (payload: CreateExamplePayload) => {
    if (!editTarget) return
    await adminApi.updateExample(editTarget.id, payload)
    await load()
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await adminApi.deleteExample(deleteTarget.id)
      setDeleteTarget(null)
      await load()
    } finally {
      setDeleting(false)
    }
  }

  const toggleActive = async (example: TemplateExample) => {
    await adminApi.updateExample(example.id, { is_active: !example.is_active })
    await load()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-muted">共 {examples.length} 条示例</p>
        <Button
          size="sm"
          onClick={() => {
            setEditTarget(null)
            setModalOpen(true)
          }}
        >
          <Plus className="h-4 w-4 mr-1" />
          新增示例
        </Button>
      </div>

      {examples.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-text-muted">
          <GripVertical className="h-10 w-10 mb-3 opacity-30" />
          <p className="text-sm">暂无 few-shot 示例，添加后可提升 LLM 提取准确率</p>
        </div>
      ) : (
        <div className="space-y-3">
          {examples.map((ex, idx) => (
            <Card
              key={ex.id}
              className={cn(
                'p-4 transition-opacity',
                !ex.is_active && 'opacity-50',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-text-muted">示例 {idx + 1}</span>
                    {!ex.is_active && (
                      <span className="rounded-full bg-bg-hover px-2 py-0.5 text-xs text-text-muted">
                        已禁用
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="mb-1 text-xs font-medium text-text-muted">输入文本</p>
                      <pre className="rounded-lg bg-bg-secondary p-3 text-xs text-text-secondary overflow-auto max-h-32 whitespace-pre-wrap break-words">
                        {ex.example_input || '（空）'}
                      </pre>
                    </div>
                    <div>
                      <p className="mb-1 text-xs font-medium text-text-muted">期望输出</p>
                      <pre className="rounded-lg bg-bg-secondary p-3 text-xs text-text-secondary overflow-auto max-h-32 whitespace-pre-wrap break-words">
                        {typeof ex.example_output === 'object'
                          ? JSON.stringify(ex.example_output, null, 2)
                          : String(ex.example_output)}
                      </pre>
                    </div>
                  </div>
                </div>
                <div className="flex flex-col gap-1 flex-shrink-0">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    title={ex.is_active ? '禁用' : '启用'}
                    onClick={() => toggleActive(ex)}
                  >
                    {ex.is_active ? (
                      <ToggleRight className="h-4 w-4 text-primary-400" />
                    ) : (
                      <ToggleLeft className="h-4 w-4 text-text-muted" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => {
                      setEditTarget(ex)
                      setModalOpen(true)
                    }}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="hover:text-error-500"
                    onClick={() => setDeleteTarget(ex)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ExampleFormModal
        open={modalOpen}
        initial={
          editTarget
            ? {
                id: editTarget.id,
                example_input: editTarget.example_input,
                example_output: editTarget.example_output,
                sort_order: editTarget.sort_order,
                is_active: editTarget.is_active,
              }
            : undefined
        }
        onClose={() => setModalOpen(false)}
        onSubmit={editTarget ? handleUpdate : handleCreate}
      />

      <Modal
        open={!!deleteTarget}
        title="删除示例"
        message="确定删除此 few-shot 示例？此操作不可恢复。"
        confirmText={deleting ? '删除中...' : '删除'}
        cancelText="取消"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </div>
  )
}

// ============ 主页面 ============

export function AdminConfig() {
  const navigate = useNavigate()
  const { profile } = useProfileStore()
  const isSuperAdmin = profile?.role === 'super_admin'
  const isTenantAdmin = profile?.role === 'tenant_admin' || isSuperAdmin

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [selectedTenantId, setSelectedTenantId] = useState<string>('')
  const [templates, setTemplates] = useState<AdminTemplate[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('')
  const [selectedTemplate, setSelectedTemplate] = useState<AdminTemplate | null>(null)
  const [loadingTemplates, setLoadingTemplates] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('feishu')

  // 权限检查
  useEffect(() => {
    if (profile && !isTenantAdmin) {
      navigate('/', { replace: true })
    }
  }, [profile, isTenantAdmin, navigate])

  // 超级管理员加载租户列表
  useEffect(() => {
    if (!isSuperAdmin) return
    api.get<Tenant[]>('/tenants').then(({ data }) => setTenants(data || []))
  }, [isSuperAdmin])

  // tenant_admin 直接使用自己的 tenant_id
  useEffect(() => {
    if (!isSuperAdmin && profile?.tenant_id) {
      setSelectedTenantId(profile.tenant_id)
    }
  }, [isSuperAdmin, profile])

  // 加载模板
  useEffect(() => {
    if (!selectedTenantId) return
    setLoadingTemplates(true)
    setSelectedTemplateId('')
    setSelectedTemplate(null)
    adminApi
      .fetchAdminTemplates(selectedTenantId)
      .then(setTemplates)
      .finally(() => setLoadingTemplates(false))
  }, [selectedTenantId])

  // 选择模板
  const handleTemplateChange = (id: string) => {
    setSelectedTemplateId(id)
    setSelectedTemplate(templates.find((t) => t.id === id) ?? null)
    setActiveTab('feishu')
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'feishu', label: '飞书表格配置' },
    { key: 'fields', label: '识别字段管理' },
    { key: 'examples', label: 'Few-shot 示例' },
  ]

  if (!profile) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center gap-3">
        <Settings className="h-6 w-6 text-primary-400" />
        <div>
          <h1 className="text-xl font-semibold text-text-primary">系统配置</h1>
          <p className="text-sm text-text-muted">配置文档模板的识别字段、审核规则和 Few-shot 示例</p>
        </div>
      </div>

      {/* 选择栏 */}
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

          <div className="min-w-[240px]">
            <Label>选择模板</Label>
            {loadingTemplates ? (
              <div className="mt-1 h-10 flex items-center px-3">
                <Spinner size="sm" />
              </div>
            ) : (
              <Select
                className="mt-1"
                value={selectedTemplateId}
                onChange={(e) => handleTemplateChange(e.target.value)}
                disabled={!selectedTenantId}
              >
                <option value="">— 请选择模板 —</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            )}
          </div>
        </div>
      </Card>

      {/* 主内容区 */}
      {selectedTemplate ? (
        <div className="space-y-4">
          {/* Tab 切换 */}
          <div className="flex gap-1 rounded-xl border border-border-default bg-bg-secondary p-1 w-fit">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
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

          {/* Tab 内容 */}
          <Card className="p-6">
            {activeTab === 'feishu' && (
              <FeishuConfigTab
                template={selectedTemplate}
                onSaved={(updated) => {
                  setSelectedTemplate(updated)
                  setTemplates((prev) => prev.map((t) => (t.id === updated.id ? { ...t, ...updated } : t)))
                }}
              />
            )}
            {activeTab === 'fields' && <FieldsTab templateId={selectedTemplate.id} />}
            {activeTab === 'examples' && <ExamplesTab templateId={selectedTemplate.id} />}
          </Card>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-24 text-text-muted">
          <Settings className="h-12 w-12 mb-4 opacity-20" />
          <p className="text-sm">
            {!selectedTenantId ? '请先选择部门' : '请选择要配置的模板'}
          </p>
        </div>
      )}
    </div>
  )
}
