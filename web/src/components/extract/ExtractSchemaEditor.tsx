import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  BUILDER_TYPES, builderIssue, builderType, fieldPath, isRecord, moveField,
  newFieldSchema, orderedProperties, parseSchemaJson, pruneUi, removeField,
  schemaAt, upsertField, type BuilderType,
} from '@/lib/extractSchema'
import type { ExtractAuthoringDefinition, ExtractSchema, ExtractSchemaUi } from '@/types/extractSchema'

interface Props {
  definition: { data_schema?: unknown; ui?: unknown; target?: unknown }
  readOnly?: boolean
  onSave: (definition: ExtractAuthoringDefinition) => Promise<void>
  onDirtyChange?: (dirty: boolean) => void
}
interface EditingField {
  parent: string
  oldKey: string | null
  key: string
  label: string
  kind: BuilderType
  hint: string
  required: boolean
  options: string
}
const control = 'w-full rounded-lg border border-border-default bg-bg-secondary px-3 py-2 text-sm text-text-primary disabled:opacity-50'

function editorIssue(schema: ExtractSchema | null): string | null {
  if (!schema) return '该配置没有 data_schema；不提供历史 fields 转换，请新建配置。'
  try { return builderIssue(schema) } catch { return 'Schema 结构不合法，请在 JSON 视图修正。' }
}
function errorText(error: unknown): string {
  const response = (error as { response?: { data?: { detail?: unknown; error?: unknown } } })?.response?.data
  const detail = response?.detail ?? response?.error
  return typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : error instanceof Error ? error.message : '保存失败'
}

export function ExtractSchemaEditor({ definition, readOnly = false, onSave, onDirtyChange }: Props) {
  const initial = isRecord(definition.data_schema) ? definition.data_schema as ExtractSchema : null
  const [schema, setSchema] = useState<ExtractSchema | null>(initial)
  const [ui, setUi] = useState<ExtractSchemaUi>(isRecord(definition.ui) ? definition.ui as ExtractSchemaUi : {})
  const [target, setTarget] = useState<'per_doc' | 'per_page'>(definition.target === 'per_page' ? 'per_page' : 'per_doc')
  const [mode, setMode] = useState<'builder' | 'json'>(editorIssue(initial) ? 'json' : 'builder')
  const [raw, setRaw] = useState(JSON.stringify(initial, null, 2))
  const [editing, setEditing] = useState<EditingField | null>(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const hasChanges = dirty || editing !== null
  const locked = readOnly || saving
  const issue = editorIssue(schema)

  useEffect(() => { onDirtyChange?.(hasChanges) }, [hasChanges, onDirtyChange])
  useEffect(() => {
    if (!hasChanges) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [hasChanges])

  const apply = (next: { schema: ExtractSchema; ui: ExtractSchemaUi }) => {
    setSchema(next.schema); setUi(next.ui); setDirty(true); setError('')
  }
  const switchMode = (next: 'builder' | 'json') => {
    if (editing || saving || next === mode) return
    setError('')
    if (next === 'json') {
      setRaw(JSON.stringify(schema, null, 2)); setMode(next)
    } else {
      try {
        const parsed = parseSchemaJson(raw)
        const problem = editorIssue(parsed)
        if (problem) throw new Error(problem)
        setSchema(parsed); setUi(pruneUi(parsed, ui)); setMode(next)
      } catch (err) { setError(errorText(err)) }
    }
  }
  const beginEdit = (parent: string, key: string | null) => {
    if (!schema || locked) return
    const object = schemaAt(schema, parent)
    const node = key === null ? newFieldSchema('text') : object.properties![key]
    const path = key === null ? '' : fieldPath(parent, key)
    setError('')
    setEditing({
      parent, oldKey: key, key: key ?? '', label: ui[path]?.label ?? key ?? '',
      kind: builderType(node) ?? 'text', hint: node.description ?? '',
      required: key !== null && !!object.required?.includes(key),
      options: node.enum?.map(String).join('\n') ?? '',
    })
  }
  const confirmEdit = () => {
    if (!schema || !editing || locked) return
    try {
      const original = editing.oldKey === null ? null : schemaAt(schema, editing.parent).properties![editing.oldKey]
      const node = original && builderType(original) === editing.kind ? { ...original } : newFieldSchema(editing.kind)
      node.description = editing.hint || editing.label || editing.key
      if (editing.kind === 'enum') {
        const options = editing.options.split(/\r?\n/).filter((line) => line !== '')
        if (!options.length || options.some((value) => !value.trim())) throw new Error('枚举至少需要一个非空选项')
        if (new Set(options).size !== options.length) throw new Error('枚举选项不能重复')
        node.enum = options // Keep spelling/whitespace exact; no semantic normalization.
      }
      apply(upsertField(schema, ui, editing.parent, editing.oldKey, editing.key, node, editing.label, editing.required))
      setEditing(null)
    } catch (err) { setError(errorText(err)) }
  }
  const save = async () => {
    if (locked || editing) return
    setSaving(true); setError('')
    try {
      const nextSchema = mode === 'json' ? parseSchemaJson(raw) : schema
      if (!nextSchema) throw new Error('缺少 data_schema，请新建配置')
      const nextUi = pruneUi(nextSchema, ui)
      await onSave({ data_schema: nextSchema, target, ui: nextUi })
      setSchema(nextSchema); setUi(nextUi); setRaw(JSON.stringify(nextSchema, null, 2)); setDirty(false)
    } catch (err) { setError(errorText(err)) }
    finally { setSaving(false) }
  }

  const renderObject = (object: ExtractSchema, parent: string) => {
    const rows = orderedProperties(object, ui, parent)
    return (
      <div className="space-y-3">
        <div className="overflow-x-auto rounded-lg border border-border-default">
          <table className="w-full text-left text-sm">
            <thead className="bg-bg-secondary text-text-muted">
              <tr><th className="px-3 py-2">字段键名</th><th className="px-3 py-2">标签</th><th className="px-3 py-2">类型</th><th className="px-3 py-2">必填</th><th className="px-3 py-2">操作</th></tr>
            </thead>
            <tbody>
              {rows.map(([key, node], index) => {
                const path = fieldPath(parent, key)
                const kind = builderType(node)
                return (
                  <tr key={key} className="border-t border-border-default">
                    <td className="px-3 py-2 font-mono text-xs" title={node.description}>{key}</td>
                    <td className="px-3 py-2">{ui[path]?.label || key}</td>
                    <td className="px-3 py-2">{kind ? BUILDER_TYPES[kind] : String(node.type)}{kind === 'object-list' ? ` · ${Object.keys(node.items?.properties ?? {}).length} 列` : ''}</td>
                    <td className="px-3 py-2">{object.required?.includes(key) ? '是' : '否'}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1">
                        <Button size="sm" variant="ghost" disabled={locked || !!editing} onClick={() => beginEdit(parent, key)}>编辑</Button>
                        <Button size="sm" variant="ghost" disabled={locked || !!editing} onClick={() => {
                          if (schema && window.confirm(`删除字段「${key}」及其子字段？保存草稿后生效。`)) apply(removeField(schema, ui, parent, key))
                        }}>删除</Button>
                        <Button size="sm" variant="ghost" aria-label={`上移 ${key}`} disabled={locked || !!editing || index === 0} onClick={() => {
                          if (schema) { setUi(moveField(schema, ui, parent, key, -1)); setDirty(true) }
                        }}>↑</Button>
                        <Button size="sm" variant="ghost" aria-label={`下移 ${key}`} disabled={locked || !!editing || index === rows.length - 1} onClick={() => {
                          if (schema) { setUi(moveField(schema, ui, parent, key, 1)); setDirty(true) }
                        }}>↓</Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {!rows.length && <p className="p-4 text-sm text-text-muted">暂无字段</p>}
        </div>
        <Button size="sm" variant="secondary" disabled={locked || !!editing} onClick={() => beginEdit(parent, null)}>
          {parent ? '添加子字段' : '添加字段'}
        </Button>
        {!parent && rows.filter(([, node]) => builderType(node) === 'object-list').map(([key, node]) => (
          <fieldset key={key} className="rounded-xl border border-border-default p-4">
            <legend className="px-2 text-sm font-semibold">{ui[fieldPath('', key)]?.label || key} · 每行的字段定义</legend>
            {renderObject(node.items!, `${fieldPath('', key)}/items`)}
          </fieldset>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2" role="tablist" aria-label="Schema 编辑方式">
          <Button role="tab" aria-selected={mode === 'builder'} variant={mode === 'builder' ? 'default' : 'secondary'} size="sm" disabled={saving || !!editing} onClick={() => switchMode('builder')}>Builder</Button>
          <Button role="tab" aria-selected={mode === 'json'} variant={mode === 'json' ? 'default' : 'secondary'} size="sm" disabled={saving || !!editing} onClick={() => switchMode('json')}>JSON</Button>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-text-muted">{hasChanges ? '未保存草稿' : '已保存的配置'} · 执行仅使用已保存内容</span>
          {!readOnly && <Button size="sm" disabled={saving || !!editing || !dirty} onClick={() => void save()}>{saving ? '保存中…' : '保存草稿'}</Button>}
        </div>
      </div>
      <p className="text-xs text-text-muted">data_schema 是唯一抽取契约。标签和排序只影响展示；找不到依据的可选字段不输出。</p>
      <label className="block space-y-1 text-sm">
        <span>抽取目标（决定结果外层，不改变字段结构）</span>
        <select className={control} value={target} disabled={locked || !!editing} onChange={(event) => { setTarget(event.target.value as 'per_doc' | 'per_page'); setDirty(true) }}>
          <option value="per_doc">整份文档 · 一个实例</option><option value="per_page">逐页 · 每页一个实例</option>
        </select>
      </label>
      {error && <p role="alert" className="rounded-lg border border-error-500/30 p-3 text-sm text-error-500">{error}</p>}
      {editing && (
        <section className="space-y-3 rounded-xl border border-primary-500/40 bg-bg-secondary p-4" aria-label="字段编辑">
          <h3 className="font-semibold">{editing.oldKey === null ? '添加字段' : `编辑 ${editing.oldKey}`}</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-sm"><span>字段键名</span><input className={control} value={editing.key} onChange={(event) => setEditing({ ...editing, key: event.target.value })} /></label>
            <label className="space-y-1 text-sm"><span>展示标签</span><input className={control} value={editing.label} onChange={(event) => setEditing({ ...editing, label: event.target.value })} /></label>
          </div>
          <label className="block space-y-1 text-sm"><span>类型</span><select className={control} value={editing.kind} onChange={(event) => setEditing({ ...editing, kind: event.target.value as BuilderType })}>
            {Object.entries(BUILDER_TYPES).filter(([kind]) => !editing.parent || kind !== 'object-list').map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
          </select></label>
          {editing.kind === 'enum' && <label className="block space-y-1 text-sm"><span>枚举候选值（每行一个，按原文拼写保存）</span><textarea className={control} rows={6} value={editing.options} onChange={(event) => setEditing({ ...editing, options: event.target.value })} /></label>}
          <label className="block space-y-1 text-sm"><span>抽取说明（写入此字段的 description）</span><textarea className={control} rows={4} value={editing.hint} onChange={(event) => setEditing({ ...editing, hint: event.target.value })} /></label>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={editing.required} onChange={(event) => setEditing({ ...editing, required: event.target.checked })} /><span>该对象内必填：缺失可能导致任务失败，不代表要求模型编造。</span></label>
          {editing.oldKey !== null && schema && builderType(schemaAt(schema, editing.parent).properties![editing.oldKey]) === 'object-list' && editing.kind !== 'object-list' && <p className="text-sm text-warning-500">改为标量将删除该列表的子字段定义和展示信息。</p>}
          <div className="flex gap-2"><Button size="sm" onClick={confirmEdit}>应用到草稿</Button><Button size="sm" variant="secondary" onClick={() => { setEditing(null); setError('') }}>取消</Button></div>
        </section>
      )}
      {mode === 'builder' && schema && !issue ? (
        <>
          <label className="block space-y-1 text-sm"><span>整体抽取说明（根 schema.description）</span><textarea className={control} rows={4} value={schema.description ?? ''} disabled={locked || !!editing} onChange={(event) => { setSchema({ ...schema, description: event.target.value }); setDirty(true) }} /></label>
          {renderObject(schema, '')}
        </>
      ) : (
        <div className="space-y-2">
          {issue && <p className="text-sm text-text-muted">{issue}</p>}
          <p className="text-xs text-text-muted">JSON 是同一份 schema 的高级编辑器。保存由后端校验；不做 fields 转换。删除或改名后，仅保留仍存在路径的展示标签。</p>
          <textarea aria-label="JSON Schema" className={`${control} min-h-[420px] font-mono text-xs`} spellCheck={false} value={raw} disabled={locked || !!editing} onChange={(event) => { setRaw(event.target.value); setDirty(true) }} />
        </div>
      )}
    </div>
  )
}
