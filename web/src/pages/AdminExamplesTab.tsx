import { useState, useEffect, useCallback } from 'react'
import * as adminApi from '@/services/admin'
import type { TemplateExample, CreateExamplePayload } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Modal } from '@/components/ui/modal'
import { Card } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { Plus, Pencil, Trash2, GripVertical, ToggleLeft, ToggleRight } from 'lucide-react'
import { cn } from '@/lib/utils'

const EMPTY_EXAMPLE: CreateExamplePayload = {
  example_input: '',
  example_output: {},
  sort_order: 0,
  is_active: true,
}

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

export function ExamplesTab({ templateId }: { templateId: string }) {
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
