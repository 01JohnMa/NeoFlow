import { useState, useEffect, useCallback } from 'react'
import * as adminApi from '@/services/admin'
import type { TemplateField, CreateFieldPayload } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Modal } from '@/components/ui/modal'
import { Spinner } from '@/components/ui/spinner'
import { Settings, Plus, Pencil, Trash2, ChevronUp, ChevronDown } from 'lucide-react'

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

interface ForceDeleteInfo {
  message: string
  non_null_count: number | null
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
              placeholder="飞书多维表格列名"
            />
          </div>
        </div>
        <div>
          <Label>提取提示</Label>
          <Input
            className="mt-1"
            value={form.extraction_hint ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, extraction_hint: e.target.value }))}
            placeholder="帮助 LLM 更准确提取该字段的提示"
          />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="review_enforced"
              checked={form.review_enforced}
              onChange={(e) => setForm((f) => ({ ...f, review_enforced: e.target.checked }))}
              className="rounded"
            />
            <Label htmlFor="review_enforced">审核时必填</Label>
          </div>
          {form.review_enforced && (
            <div className="mt-2">
              <Label>允许值（留空表示不限制）</Label>
              <div className="mt-1 flex gap-2">
                <Input
                  value={allowedInput}
                  onChange={(e) => setAllowedInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addAllowedValue()}
                  placeholder="输入后按 Enter 添加"
                />
                <Button type="button" size="sm" onClick={addAllowedValue}>
                  添加
                </Button>
              </div>
              {allowedValues.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {allowedValues.map((v) => (
                    <span
                      key={v}
                      className="inline-flex items-center gap-1 rounded-full bg-primary-500/10 px-2 py-0.5 text-xs text-primary-400"
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

export function FieldsTab({ templateId }: { templateId: string }) {
  const [fields, setFields] = useState<TemplateField[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<TemplateField | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<TemplateField | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [forceDeleteInfo, setForceDeleteInfo] = useState<ForceDeleteInfo | null>(null)

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

  const handleDelete = async (force = false) => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await adminApi.deleteField(deleteTarget.id, force)
      setDeleteTarget(null)
      setForceDeleteInfo(null)
      await load()
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: { message?: string; non_null_count?: number } } } }
      if (axiosErr?.response?.status === 409) {
        const detail = axiosErr.response.data?.detail
        setForceDeleteInfo({
          message: detail?.message ?? '该列存在历史数据，删除将永久丢失',
          non_null_count: detail?.non_null_count ?? null,
        })
      } else {
        throw err
      }
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
        open={!!deleteTarget && !forceDeleteInfo}
        title="删除字段"
        message={`确定删除字段「${deleteTarget?.field_label}」？对应数据库列也将同步删除，此操作不可恢复。`}
        confirmText={deleting ? '删除中...' : '删除'}
        cancelText="取消"
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => handleDelete(false)}
      />

      <Modal
        open={!!forceDeleteInfo}
        title="⚠️ 存在历史数据，确认强制删除？"
        message={
          forceDeleteInfo
            ? `${forceDeleteInfo.message}${forceDeleteInfo.non_null_count != null ? `（共 ${forceDeleteInfo.non_null_count} 条）` : ''}。\n强制删除后数据将永久丢失，无法恢复，请确认！`
            : ''
        }
        confirmText={deleting ? '强制删除中...' : '强制删除'}
        cancelText="取消"
        onClose={() => {
          setForceDeleteInfo(null)
          setDeleteTarget(null)
        }}
        onConfirm={() => handleDelete(true)}
      />
    </div>
  )
}
