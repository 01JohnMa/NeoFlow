import { ExtractSchemaEditor } from '@/components/extract/ExtractSchemaEditor'
import { useState } from 'react'
import * as configurationsApi from '@/services/configurations'
import type {
  Configuration,
  ConfigurationField,
  ConfigurationFieldPayload,
} from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Modal } from '@/components/ui/modal'
import { Settings, Plus, Pencil, Trash2, ChevronUp, ChevronDown } from 'lucide-react'

const EMPTY_FIELD: ConfigurationFieldPayload = {
  field_key: '',
  field_label: '',
  field_type: 'text',
  extraction_hint: '',
  sort_order: 0,
}

function FieldFormModal({
  open,
  initial,
  onClose,
  onSubmit,
}: {
  open: boolean
  initial?: Partial<ConfigurationFieldPayload> & { id?: string }
  onClose: () => void
  onSubmit: (data: ConfigurationFieldPayload) => Promise<void>
}) {
  const [form, setForm] = useState<ConfigurationFieldPayload>({ ...EMPTY_FIELD, ...initial })
  const [submitting, setSubmitting] = useState(false)

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
        <div>
          <Label>字段类型</Label>
          <Select
            className="mt-1"
            value={form.field_type}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                field_type: e.target.value as ConfigurationField['field_type'],
              }))
            }
          >
            <option value="text">文本</option>
            <option value="date">日期</option>
            <option value="number">数值</option>
            <option value="boolean">布尔</option>
          </Select>
        </div>
        <div>
          <Label>字段描述</Label>
          <Input
            className="mt-1"
            value={form.extraction_hint ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, extraction_hint: e.target.value }))}
            placeholder="描述取值线索；验证过的示例也写在这里"
          />
        </div>
      </div>
    </Modal>
  )
}

function toConfigurationField(
  payload: ConfigurationFieldPayload,
  index: number,
  base?: ConfigurationField,
): ConfigurationField {
  return {
    field_key: payload.field_key,
    field_label: payload.field_label,
    field_type: payload.field_type,
    extraction_hint: payload.extraction_hint ?? '',
    sort_order: index,
    is_required: base?.is_required ?? false,
    default_value: base?.default_value ?? null,
    source_doc_type: base?.source_doc_type ?? null,
  }
}

function FlatFieldsTab({
  configuration,
  onUpdated,
}: {
  configuration: Configuration
  onUpdated: (configuration: Configuration) => void
}) {
  const fields = configuration.draft_definition?.fields ?? []
  const [modalOpen, setModalOpen] = useState(false)
  const [editIndex, setEditIndex] = useState<number | null>(null)
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)

  const saveFields = async (nextFields: ConfigurationField[]) => {
    setSaving(true)
    try {
      const updated = await configurationsApi.updateConfiguration(configuration.id, {
        definition: { fields: nextFields },
      })
      onUpdated(updated)
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async (payload: ConfigurationFieldPayload) => {
    await saveFields([...fields, toConfigurationField(payload, fields.length)])
  }

  const handleUpdate = async (payload: ConfigurationFieldPayload) => {
    if (editIndex === null) return
    const next = fields.map((field, index) =>
      index === editIndex ? toConfigurationField(payload, index, field) : field,
    )
    await saveFields(next)
  }

  const handleDelete = async () => {
    if (deleteIndex === null) return
    setSaving(true)
    try {
      const next = fields
        .filter((_, index) => index !== deleteIndex)
        .map((field, index) => ({ ...field, sort_order: index }))
      const updated = await configurationsApi.updateConfiguration(configuration.id, {
        definition: { fields: next },
      })
      setDeleteIndex(null)
      onUpdated(updated)
    } finally {
      setSaving(false)
    }
  }

  const moveField = async (index: number, direction: 'up' | 'down') => {
    const swapIndex = direction === 'up' ? index - 1 : index + 1
    if (swapIndex < 0 || swapIndex >= fields.length) return
    const next = [...fields]
    ;[next[index], next[swapIndex]] = [next[swapIndex], next[index]]
    await saveFields(next.map((field, i) => ({ ...field, sort_order: i })))
  }

  const editTarget = editIndex === null ? null : fields[editIndex]
  const deleteTarget = deleteIndex === null ? null : fields[deleteIndex]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-muted">共 {fields.length} 个字段</p>
        <Button
          size="sm"
          disabled={saving}
          onClick={() => {
            setEditIndex(null)
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
                <th className="px-3 py-2 text-left font-medium">提取提示</th>
                <th className="px-3 py-2 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field, idx) => (
                <tr
                  key={`${field.field_key}-${idx}`}
                  className="border-b border-border-default last:border-0 hover:bg-bg-hover transition-colors"
                >
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-0.5">
                      <button
                        onClick={() => moveField(idx, 'up')}
                        disabled={idx === 0 || saving}
                        className="text-text-muted hover:text-text-primary disabled:opacity-20"
                      >
                        <ChevronUp className="h-3 w-3" />
                      </button>
                      <button
                        onClick={() => moveField(idx, 'down')}
                        disabled={idx === fields.length - 1 || saving}
                        className="text-text-muted hover:text-text-primary disabled:opacity-20"
                      >
                        <ChevronDown className="h-3 w-3" />
                      </button>
                    </div>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-primary-400">{field.field_key}</td>
                  <td className="px-3 py-2 text-text-primary">{field.field_label}</td>
                  <td className="px-3 py-2 text-text-secondary">
                    {{ text: '文本', date: '日期', number: '数值', boolean: '布尔' }[field.field_type] ??
                      field.field_type}
                  </td>
                  <td className="px-3 py-2 text-text-muted text-xs max-w-[160px] truncate">
                    {field.extraction_hint || '-'}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        disabled={saving}
                        onClick={() => {
                          setEditIndex(idx)
                          setModalOpen(true)
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="hover:text-error-500"
                        disabled={saving}
                        onClick={() => setDeleteIndex(idx)}
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

      {modalOpen && (
        <FieldFormModal
          open
          initial={
            editTarget
              ? {
                  id: editTarget.field_key,
                  ...editTarget,
                  extraction_hint: editTarget.extraction_hint ?? undefined,
                }
              : undefined
          }
          onClose={() => setModalOpen(false)}
          onSubmit={editIndex === null ? handleCreate : handleUpdate}
        />
      )}

      <Modal
        open={deleteTarget !== null}
        title="删除字段"
        message={`确定删除字段「${deleteTarget?.field_label ?? ''}」？此操作不可恢复。`}
        confirmText={saving ? '删除中...' : '删除'}
        cancelText="取消"
        onClose={() => setDeleteIndex(null)}
        onConfirm={handleDelete}
      />
    </div>
  )
}

/** Extract edits the schema directly. Flat fields are only for other operation types. */
export function FieldsTab({ configuration, onUpdated, onDirtyChange }: {
  configuration: Configuration
  onUpdated: (configuration: Configuration) => void
  onDirtyChange?: (dirty: boolean) => void
}) {
  if (configuration.type !== 'extract') return <FlatFieldsTab configuration={configuration} onUpdated={onUpdated} />
  return (
    <ExtractSchemaEditor
      key={`${configuration.id}:${configuration.updated_at}`}
      definition={configuration.draft_definition}
      readOnly={configuration.status === 'archived'}
      onDirtyChange={onDirtyChange}
      onSave={async (definition) => {
        const updated = await configurationsApi.updateConfiguration(configuration.id, { definition })
        onUpdated(updated)
      }}
    />
  )
}
