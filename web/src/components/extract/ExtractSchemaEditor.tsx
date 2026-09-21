import { Fragment, useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import {
  BUILDER_TYPES, builderIssue, builderType, fieldPath, isRecord, moveField,
  orderedProperties, parseSchemaJson, pruneUi, removeField, schemaAt, upsertField,
  type BuilderType,
} from '@/lib/extractSchema'
import {
  changeFieldType, childObject, enumOptions, inlineErrors, insertField, inside, materializeDraft,
  objectPath, type InlineBuffers, type InlineError,
} from '@/lib/extractInlineDraft'
import type { ExtractAuthoringDefinition, ExtractSchema, ExtractSchemaUi } from '@/types/extractSchema'

interface Props {
  definition: { data_schema?: unknown; ui?: unknown; target?: unknown }
  readOnly?: boolean
  onSave: (definition: ExtractAuthoringDefinition) => Promise<void>
  onDirtyChange?: (dirty: boolean) => void
}
interface Draft {
  schema: ExtractSchema | null
  ui: ExtractSchemaUi
  target: 'per_doc' | 'per_page'
  buffers: InlineBuffers
}
const control = 'w-full rounded-md border border-border-default bg-bg-secondary px-2 py-1.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:opacity-50'
const cellControl = `${control} border-transparent bg-transparent hover:border-border-default`
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T

function initialDraft(definition: Props['definition']): Draft {
  return {
    schema: isRecord(definition.data_schema) ? clone(definition.data_schema) as ExtractSchema : null,
    ui: isRecord(definition.ui) ? clone(definition.ui) as ExtractSchemaUi : {},
    target: definition.target === 'per_page' ? 'per_page' : 'per_doc', buffers: {},
  }
}
function issue(schema: ExtractSchema | null): string | null {
  if (!schema) return '配置缺少 data_schema，请新建配置；不提供旧 fields 转换。'
  try { return builderIssue(schema) } catch { return 'Schema 结构不合法，请在 JSON 视图修正。' }
}
function errorText(error: unknown): string {
  const response = (error as { response?: { data?: { detail?: unknown; error?: unknown } } })?.response?.data
  const detail = response?.detail ?? response?.error
  return typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : error instanceof Error ? error.message : '保存失败'
}
function finishSingleLine(event: KeyboardEvent<HTMLInputElement>): void {
  if (event.key === 'Enter' && !event.nativeEvent.isComposing && event.keyCode !== 229) {
    event.preventDefault(); event.currentTarget.blur()
  }
}

export function ExtractSchemaEditor({ definition, readOnly = false, onSave, onDirtyChange }: Props) {
  const [draft, setDraft] = useState(() => initialDraft(definition))
  const live = useRef(draft)
  const baseline = useRef(draft)
  const [mode, setMode] = useState<'builder' | 'json'>(() => issue(draft.schema) ? 'json' : 'builder')
  const [raw, setRaw] = useState(() => JSON.stringify(draft.schema, null, 2))
  const rawRef = useRef(raw)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [pinned, setPinned] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [details, setDetails] = useState<Record<string, boolean>>({})
  const [optionsOpen, setOptionsOpen] = useState<Record<string, boolean>>({})
  const [menu, setMenu] = useState<string | null>(null)
  const [newKind, setNewKind] = useState<BuilderType>('text')
  const [focus, setFocus] = useState<{ path: string; input: 'key' | 'options'; select?: boolean } | null>(null)
  const root = useRef<HTMLDivElement>(null)
  const idPrefix = useId()
  const ids = useRef(new Map<string, string>())
  const nextId = useRef(0)
  const locked = readOnly || saving
  const errors = mode === 'builder' && draft.schema ? inlineErrors(draft.schema, draft.buffers) : []
  const rowId = (path: string) => {
    if (!ids.current.has(path)) ids.current.set(path, `${idPrefix}-field-${nextId.current++}`)
    return ids.current.get(path)!
  }

  useEffect(() => { onDirtyChange?.(dirty) }, [dirty, onDirtyChange])
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  useEffect(() => {
    if (!focus) return
    const frame = requestAnimationFrame(() => {
      const id = ids.current.get(focus.path)
      const input = id && document.getElementById(`${id}-${focus.input}`) as HTMLInputElement | HTMLTextAreaElement | null
      if (input) {
        input.focus({ preventScroll: true })
        input.scrollIntoView({ block: 'nearest', inline: 'nearest' })
        if (focus.select) input.select()
      }
    })
    return () => cancelAnimationFrame(frame)
  }, [focus])

  const change = (fn: (current: Draft) => Draft) => {
    if (readOnly || savingRef.current) return
    const next = fn(live.current)
    live.current = next; setDraft(next); setDirty(true); setError('')
  }
  const buffer = (path: string, patch: InlineBuffers[string]) => change((current) => ({
    ...current, buffers: { ...current.buffers, [path]: { ...current.buffers[path], ...patch } },
  }))
  const updateField = (parent: string, key: string, patch: Partial<ExtractSchema>, required?: boolean) => change((current) => {
    if (!current.schema) return current
    const path = fieldPath(parent, key)
    const object = schemaAt(current.schema, parent)
    const next = upsertField(current.schema, current.ui, parent, key, key,
      { ...schemaAt(current.schema, path), ...patch }, current.ui[path]?.label ?? '',
      required ?? !!object.required?.includes(key))
    // Editing a value must not reorder an imported field without UI order metadata.
    next.ui[path] = { ...current.ui[path] }
    return { ...current, ...next }
  })
  const remapVisual = (remap: (path: string) => string) => {
    const mapping = (current: Record<string, boolean>) => Object.fromEntries(Object.entries(current).map(([p, value]) => [remap(p), value]))
    setExpanded(mapping); setDetails(mapping); setOptionsOpen(mapping)
    setPinned((p) => p === null ? null : remap(p))
    setMenu(null)
    ids.current = new Map([...ids.current].map(([p, id]) => [remap(p), id]))
  }
  const locate = (problem: InlineError) => {
    setQuery(''); setPinned(problem.path)
    setExpanded((current) => ({ ...current, ...Object.fromEntries([...ids.current.keys()].filter((p) => inside(problem.path, p)).map((p) => [p, true])) }))
    if (problem.input === 'options') setOptionsOpen((current) => ({ ...current, [problem.path]: true }))
    setFocus({ ...problem })
  }
  const save = async () => {
    if (readOnly || savingRef.current) return
    const current = live.current
    if (mode === 'builder' && current.schema) {
      const problems = inlineErrors(current.schema, current.buffers)
      if (problems.length) { locate(problems[0]); return }
    }
    savingRef.current = true; setSaving(true); setError('')
    try {
      const next = mode === 'json'
        ? { schema: parseSchemaJson(rawRef.current), ui: current.ui, paths: {} as Record<string, string> }
        : current.schema ? materializeDraft(current.schema, current.ui, current.buffers) : null
      if (!next) throw new Error('缺少 data_schema，请新建配置')
      const ui = pruneUi(next.schema, next.ui)
      await onSave({ data_schema: next.schema, ui, target: current.target })
      remapVisual((p) => next.paths[p] ?? p)
      const saved: Draft = { schema: next.schema, ui, target: current.target, buffers: {} }
      live.current = saved; baseline.current = saved; setDraft(saved)
      rawRef.current = JSON.stringify(next.schema, null, 2); setRaw(rawRef.current); setDirty(false)
    } catch (err) { setError(errorText(err)) }
    finally { savingRef.current = false; setSaving(false) }
  }
  // Read live refs so keyboard save includes the focused input's most recent onChange.
  const saveRef = useRef(save)
  saveRef.current = save
  useEffect(() => {
    const shortcut = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && !event.isComposing && root.current?.contains(document.activeElement)) {
        event.preventDefault(); void saveRef.current()
      }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [])

  const switchMode = (nextMode: 'builder' | 'json') => {
    if (savingRef.current || nextMode === mode) return
    try {
      const current = live.current
      if (nextMode === 'json') {
        if (!current.schema) throw new Error('缺少 data_schema')
        const problems = inlineErrors(current.schema, current.buffers)
        if (problems.length) { locate(problems[0]); return }
        const next = materializeDraft(current.schema, current.ui, current.buffers)
        remapVisual((p) => next.paths[p] ?? p)
        live.current = { ...current, ...next, buffers: {} }; setDraft(live.current)
        rawRef.current = JSON.stringify(next.schema, null, 2); setRaw(rawRef.current)
      } else {
        const schema = parseSchemaJson(rawRef.current)
        const problem = issue(schema)
        if (problem) throw new Error(problem)
        live.current = { ...current, schema, ui: pruneUi(schema, current.ui), buffers: {} }; setDraft(live.current)
      }
      setMode(nextMode); setError('')
    } catch (err) { setError(errorText(err)) }
  }
  const add = (parent: string, kind: BuilderType, after: string | null = null, source?: string) => {
    if (!live.current.schema || locked) return
    try {
      const next = insertField({ schema: live.current.schema, ui: live.current.ui }, parent, kind, after, live.current.buffers, source)
      change((current) => ({ ...current, schema: next.schema, ui: next.ui, buffers: next.buffers }))
      setQuery(''); setPinned(next.path); setMenu(null)
      if (childObject(schemaAt(next.schema, next.path))) setExpanded((current) => ({ ...current, [next.path]: true }))
      if (kind === 'enum') setOptionsOpen((current) => ({ ...current, [next.path]: true }))
      setFocus({ path: next.path, input: 'key', select: true })
    } catch (err) { setError(errorText(err)) }
  }
  const setType = (parent: string, key: string, kind: BuilderType) => {
    if (!live.current.schema || locked) return
    const path = fieldPath(parent, key)
    const original = schemaAt(live.current.schema, path)
    if (builderType(original) === kind) return
    if (childObject(original) && !window.confirm(kind === 'object' || kind === 'object-list'
      ? '此操作会改变该字段的结果结构，保留子字段定义。继续？'
      : '改为标量将删除所有子字段定义。继续？')) return
    const next = changeFieldType({ schema: live.current.schema, ui: live.current.ui }, parent, key, kind, live.current.buffers)
    remapVisual(next.remap)
    change((current) => ({ ...current, schema: next.schema, ui: next.ui, buffers: next.buffers }))
    if (childObject(schemaAt(next.schema, path))) setExpanded((current) => ({ ...current, [path]: true }))
    setOptionsOpen((current) => ({ ...current, [path]: kind === 'enum' }))
  }
  const discard = () => {
    if (locked || !window.confirm('放弃全部未保存修改？')) return
    const saved = clone(baseline.current)
    live.current = saved; setDraft(saved); setDirty(false); setError(''); setMenu(null)
    rawRef.current = JSON.stringify(saved.schema, null, 2); setRaw(rawRef.current)
    if (mode === 'builder' && issue(saved.schema)) setMode('json')
  }
  const matches = (key: string, node: ExtractSchema, path: string): boolean => {
    const text = `${key} ${draft.buffers[path]?.key ?? ''} ${draft.ui[path]?.label ?? ''}`.toLocaleLowerCase()
    if (!query.trim() || text.includes(query.trim().toLocaleLowerCase()) || pinned === path) return true
    const object = childObject(node)
    return !!object && Object.entries(object.properties ?? {}).some(([name, child]) => matches(name, child, fieldPath(objectPath(path, node), name)))
  }

  const renderRows = (object: ExtractSchema, parent: string, depth = 0, ancestorMatches = false): ReactNode => {
    const entries = orderedProperties(object, draft.ui, parent)
    return entries.map(([key, node], index) => {
      const path = fieldPath(parent, key)
      const id = rowId(path)
      if (!ancestorMatches && !matches(key, node, path)) return null
      const label = draft.ui[path]?.label || draft.buffers[path]?.key || key
      const kind = builderType(node)
      const children = childObject(node)
      const open = !!children && (!!expanded[path] || !!query.trim())
      const keyError = errors.find((item) => item.path === path && item.input === 'key')
      const optionsError = errors.find((item) => item.path === path && item.input === 'options')
      return (
        <Fragment key={id}>
          <tr data-field-path={path} onFocusCapture={() => setPinned(path)} className="border-t border-border-default align-top">
            <td className="px-2 py-2" style={{ paddingLeft: 8 + depth * 24 }}>
              <div className="flex items-center gap-1">
                {children && <button type="button" aria-label={`展开 ${label}`} aria-expanded={open} className="px-1 py-1.5 text-text-muted" onClick={() => setExpanded((current) => ({ ...current, [path]: !open }))}>{open ? '▾' : '▸'}</button>}
                <input id={`${id}-key`} aria-label="字段键名" aria-invalid={!!keyError} aria-describedby={keyError ? `${id}-key-error` : undefined} className={`${cellControl} min-w-[150px] font-mono text-xs`} value={draft.buffers[path]?.key ?? key} disabled={locked} onChange={(event) => buffer(path, { key: event.target.value })} onKeyDown={finishSingleLine} />
              </div>
              {keyError && <p id={`${id}-key-error`} className="mt-1 text-xs text-error-500">{keyError.message}</p>}
            </td>
            <td className="px-2 py-2"><input aria-label="展示标签" className={`${cellControl} min-w-[100px]`} value={draft.ui[path]?.label ?? ''} placeholder={key} disabled={locked} onChange={(event) => {
              const label = event.target.value
              change((current) => ({ ...current, ui: { ...current.ui, [path]: { ...current.ui[path], label } } }))
            }} onKeyDown={finishSingleLine} /></td>
            <td className="px-2 py-2">
              <button type="button" aria-label={`抽取说明 ${label}`} aria-expanded={!!details[path]} className="min-h-9 w-full rounded-md px-2 py-1.5 text-left text-xs text-text-muted hover:bg-bg-hover focus-visible:ring-1 focus-visible:ring-primary-500" onClick={() => setDetails((current) => ({ ...current, [path]: !current[path] }))}>
                <span className="line-clamp-2">{node.description || '添加抽取说明'}</span>
              </button>
            </td>
            <td className="px-2 py-2">
              <select aria-label="字段类型" className={`${cellControl} min-w-[115px]`} value={kind} disabled={locked} onChange={(event) => setType(parent, key, event.target.value as BuilderType)}>
                {Object.entries(BUILDER_TYPES).filter(([type]) => !depth || (type !== 'object' && type !== 'object-list')).map(([type, name]) => <option key={type} value={type}>{name}</option>)}
              </select>
              {children && <span className="px-2 text-xs text-text-muted">{Object.keys(children.properties ?? {}).length} 个子字段</span>}
              {kind === 'enum' && <button type="button" aria-label={`候选值 ${label}`} aria-expanded={!!optionsOpen[path]} className={`px-2 text-xs ${optionsError ? 'text-error-500' : 'text-primary-400'}`} onClick={() => setOptionsOpen((current) => ({ ...current, [path]: !current[path] }))}>{optionsError ? '候选值待修正' : `${draft.buffers[path]?.options === undefined ? node.enum?.length ?? 0 : enumOptions(draft.buffers[path].options!).length} 项 · 编辑候选值`}</button>}
            </td>
            <td className="px-3 py-3.5"><input aria-label="必填" title="缺失可能导致任务失败，不代表要求模型编造" type="checkbox" checked={!!object.required?.includes(key)} disabled={locked} onChange={(event) => updateField(parent, key, {}, event.target.checked)} /></td>
            <td className="px-2 py-2"><div className="flex items-center gap-1">
              {children && <Button size="sm" variant="ghost" disabled={locked} onClick={() => { setExpanded((current) => ({ ...current, [path]: true })); add(objectPath(path, node), 'text') }}>＋子字段</Button>}
              <Button size="sm" variant="ghost" aria-label={`更多 ${label}`} aria-expanded={menu === path} disabled={locked} onClick={() => setMenu(menu === path ? null : path)}>⋯</Button>
            </div></td>
          </tr>
          {menu === path && <tr><td colSpan={6} className="border-t border-border-default bg-bg-secondary px-4 py-2"><div className="flex flex-wrap gap-2" aria-label={`操作 ${label}`}>
            <Button size="sm" variant="ghost" disabled={locked} onClick={() => add(parent, kind ?? 'text', key, key)}>复制字段</Button>
            <Button size="sm" variant="ghost" disabled={locked} onClick={() => add(parent, 'text', key)}>在下方插入</Button>
            {[-1, 1].map((direction) => <Button key={direction} size="sm" variant="ghost" disabled={locked || (direction < 0 ? index === 0 : index === entries.length - 1)} onClick={() => change((current) => ({ ...current, ui: moveField(current.schema!, current.ui, parent, key, direction as -1 | 1) }))}>{direction < 0 ? '上移' : '下移'}</Button>)}
            <Button size="sm" variant="ghost" disabled={locked} onClick={() => {
              if (!window.confirm(`删除字段「${label}」${children ? '及全部子字段' : ''}？保存草稿后生效。`)) return
              change((current) => ({ ...current, ...removeField(current.schema!, current.ui, parent, key), buffers: Object.fromEntries(Object.entries(current.buffers).filter(([p]) => !inside(p, path))) }))
              setMenu(null)
            }}>删除字段</Button>
            <Button size="sm" variant="ghost" onClick={() => setMenu(null)}>收起操作</Button>
          </div></td></tr>}
          {details[path] && <tr><td colSpan={6} className="bg-bg-secondary px-4 py-3"><label className="block space-y-1 text-xs text-text-muted"><span>{label} · 抽取说明</span><textarea aria-label={`编辑抽取说明 ${label}`} className={control} rows={3} value={node.description ?? ''} disabled={locked} onChange={(event) => updateField(parent, key, { description: event.target.value })} /></label></td></tr>}
          {kind === 'enum' && optionsOpen[path] && <tr><td colSpan={6} className="bg-bg-secondary px-4 py-3">
            <label className="block space-y-1 text-xs text-text-muted"><span>{label} · 枚举候选值，每行一个，可批量粘贴；拼写原样保存</span><textarea id={`${id}-options`} aria-label={`编辑候选值 ${label}`} aria-invalid={!!optionsError} aria-describedby={optionsError ? `${id}-options-error` : undefined} className={control} rows={4} value={draft.buffers[path]?.options ?? node.enum?.map(String).join('\n') ?? ''} disabled={locked} onChange={(event) => buffer(path, { options: event.target.value })} /></label>
            {optionsError && <p id={`${id}-options-error`} className="mt-1 text-xs text-error-500">{optionsError.message}</p>}
          </td></tr>}
          {open && <>
            {renderRows(children!, objectPath(path, node), depth + 1, ancestorMatches || `${key} ${draft.ui[path]?.label ?? ''}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))}
            <tr><td colSpan={6} className="border-t border-border-default px-8 py-2"><Button size="sm" variant="ghost" disabled={locked} onClick={() => add(objectPath(path, node), 'text')}>＋ 添加子字段</Button><span className="ml-3 text-xs text-text-muted">{kind === 'object-list' ? '定义每条记录的结构，不在这里录入实际产品' : '此对象内的字段定义'}</span></td></tr>
          </>}
        </Fragment>
      )
    })
  }

  return (
    <div ref={root} className="relative space-y-4" data-testid="extract-schema-editor">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2" role="tablist" aria-label="Schema 编辑方式">
          <Button role="tab" aria-selected={mode === 'builder'} variant={mode === 'builder' ? 'default' : 'secondary'} size="sm" disabled={saving} onClick={() => switchMode('builder')}>Builder</Button>
          <Button role="tab" aria-selected={mode === 'json'} variant={mode === 'json' ? 'default' : 'secondary'} size="sm" disabled={saving} onClick={() => switchMode('json')}>JSON</Button>
        </div>
        {mode === 'builder' && <div className="flex flex-wrap items-center gap-2">
          <input aria-label="搜索字段" className={control} style={{ width: 210 }} placeholder="搜索标签或键名" value={query} onChange={(event) => { setQuery(event.target.value); setPinned(null) }} />
          <span className="text-xs text-text-muted">{Object.keys(draft.schema?.properties ?? {}).length} 个顶层字段</span>
          {!readOnly && <><select aria-label="新增字段类型" className={control} style={{ width: 120 }} value={newKind} disabled={locked} onChange={(event) => setNewKind(event.target.value as BuilderType)}>{Object.entries(BUILDER_TYPES).map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}</select><Button size="sm" disabled={locked} onClick={() => add('', newKind)}>新增字段</Button></>}
        </div>}
      </div>
      <details className="rounded-lg border border-border-default p-3">
        <summary className="cursor-pointer text-sm text-text-secondary">整体抽取说明与目标 <span className="ml-2 text-xs text-text-muted">{draft.target === 'per_doc' ? '整份文档' : '逐页'}</span></summary>
        <div className="mt-3 space-y-3">
          <label className="block space-y-1 text-sm"><span>抽取目标</span><select aria-label="抽取目标" className={control} value={draft.target} disabled={locked} onChange={(event) => { const target = event.target.value as Draft['target']; change((current) => ({ ...current, target })) }}><option value="per_doc">整份文档 · 一个实例</option><option value="per_page">逐页 · 每页一个实例</option></select></label>
          {mode === 'builder' && <label className="block space-y-1 text-sm"><span>整体抽取说明</span><textarea aria-label="整体抽取说明" className={control} rows={3} value={draft.schema?.description ?? ''} disabled={locked} onChange={(event) => { const description = event.target.value; change((current) => ({ ...current, schema: { ...current.schema, description } })) }} /></label>}
          <p className="text-xs text-text-muted">说明写入 schema.description。找不到依据的可选字段省略；必填不代表允许编造。</p>
        </div>
      </details>
      {mode === 'builder' && draft.schema ? <>
        <div className="overflow-x-auto rounded-lg border border-border-default">
          <table className="w-full min-w-[850px] table-fixed text-left text-sm"><thead className="bg-bg-secondary text-text-muted"><tr>
            <th className="w-[23%] px-3 py-2">字段键名</th><th className="w-[16%] px-3 py-2">标签</th><th className="w-[25%] px-3 py-2">抽取说明</th><th className="w-[17%] px-3 py-2">类型</th><th className="w-[6%] px-3 py-2">必填</th><th className="w-[13%] px-3 py-2">操作</th>
          </tr></thead><tbody>{renderRows(draft.schema, '')}</tbody></table>
          {!Object.entries(draft.schema.properties ?? {}).some(([key, node]) => matches(key, node, fieldPath('', key))) && <p className="p-6 text-center text-sm text-text-muted">{query ? '没有匹配的字段' : '暂无字段，点击新增字段开始配置'}</p>}
        </div>
        {!readOnly && <Button size="sm" variant="secondary" disabled={locked} onClick={() => add('', newKind)}>＋ 添加字段</Button>}
      </> : <div className="space-y-2">
        {issue(draft.schema) && <p className="text-sm text-text-muted">{issue(draft.schema)}</p>}
        <p className="text-xs text-text-muted">同一份 schema 的高级编辑视图，保存由后端校验。不转换历史 fields；手动删除或改名后仅保留有效路径的展示标签。</p>
        <textarea aria-label="JSON Schema" className={`${control} min-h-[420px] font-mono text-xs`} spellCheck={false} value={raw} disabled={locked} onChange={(event) => { rawRef.current = event.target.value; setRaw(event.target.value); setDirty(true); setError('') }} />
      </div>}
      <div data-testid="save-bar" className="sticky bottom-0 z-20 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-default bg-bg-card p-3 shadow-lg">
        <div className="min-w-0 flex-1" aria-live="polite">
          <p className="text-sm text-text-secondary">{saving ? '保存中…' : dirty ? '有未保存修改' : '已保存'} <span className="text-xs text-text-muted">· 执行使用已保存内容</span></p>
          {errors.length > 0 && <button type="button" className="text-xs text-error-500 underline" onClick={() => locate(errors[0])}>有 {errors.length} 处错误，点击定位</button>}
          {error && <p role="alert" className="mt-1 break-words text-xs text-error-500">{error}</p>}
        </div>
        {!readOnly && <div className="flex gap-2"><Button size="sm" variant="secondary" disabled={locked || !dirty} onClick={discard}>放弃修改</Button><Button size="sm" disabled={locked || !dirty || errors.length > 0} onClick={() => void save()}>{saving ? '保存中…' : '保存草稿'}</Button></div>}
      </div>
    </div>
  )
}
