import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { fieldPath, isRecord, orderedProperties, own } from '@/lib/extractSchema'
import type { ExtractSchema, ExtractSchemaUi, ExtractResultView as ResultView } from '@/types/extractSchema'

export interface ExtractResultViewProps { data: unknown; view?: ResultView | null }

function JsonValue({ value }: { value: unknown }) {
  return <pre className="whitespace-pre-wrap break-words font-mono text-xs">{JSON.stringify(value, null, 2)}</pre>
}
function Missing() {
  return <span className="text-text-muted" title="本次结果没有该字段；不能据此判断原文不存在、模型遗漏或无法归一。">未返回</span>
}
function FieldValue({ present, value, schema, path, ui }: {
  present: boolean; value: unknown; schema: ExtractSchema; path: string; ui: ExtractSchemaUi
}) {
  if (!present) return <Missing />
  if (schema.type === 'array' && schema.items?.type === 'object' && Array.isArray(value)) {
    if (value.length === 0) return <JsonValue value={value} />
    const parent = `${path}/items`
    const columns = orderedProperties(schema.items, ui, parent)
    if (!value.every(isRecord)) return <JsonValue value={value} />
    // Preserve additional returned keys instead of hiding data outside the declared columns.
    const extra = [...new Set(value.flatMap((row) => Object.keys(row)))].filter((key) => !own(schema.items!.properties ?? {}, key)).sort()
    return (
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead><tr><th className="border-b border-border-default p-2">行</th>{columns.map(([key]) => <th className="border-b border-border-default p-2" key={key}>{ui[fieldPath(parent, key)]?.label || key}</th>)}{extra.map((key) => <th className="border-b border-border-default p-2" key={key}>{key}（额外返回）</th>)}</tr></thead>
          <tbody>{value.map((row, index) => <tr key={index}>
            <td className="border-b border-border-default p-2">{index + 1}</td>
            {columns.map(([key, node]) => <td className="border-b border-border-default p-2 align-top" key={key}><FieldValue present={own(row, key)} value={row[key]} schema={node} path={fieldPath(parent, key)} ui={ui} /></td>)}
            {extra.map((key) => <td className="border-b border-border-default p-2 align-top" key={key}>{own(row, key) ? <JsonValue value={row[key]} /> : <Missing />}</td>)}
          </tr>)}</tbody>
        </table>
      </div>
    )
  }
  return <JsonValue value={value} /> // false, 0, null, "", [], {} are all real returned values.
}
function Instance({ data, schema, ui }: { data: unknown; schema: ExtractSchema; ui: ExtractSchemaUi }) {
  if (!isRecord(data)) return <div><p className="text-sm text-warning-500">结果实例不是对象，按原始值展示。</p><JsonValue value={data} /></div>
  const fields = orderedProperties(schema, ui)
  const returned = fields.filter(([key]) => own(data, key)).length
  const extra = Object.keys(data).filter((key) => !own(schema.properties ?? {}, key)).sort()
  return (
    <div className="space-y-2">
      <p className="text-xs text-text-muted">返回 {returned}/{fields.length} 个声明的顶层字段（覆盖数量，不是准确率）</p>
      <div className="overflow-x-auto rounded-lg border border-border-default">
        <table className="w-full text-left text-sm">
          <thead className="bg-bg-secondary"><tr><th className="p-3">字段</th><th className="p-3">本次返回值</th></tr></thead>
          <tbody>
            {fields.map(([key, node]) => <tr key={key} className="border-t border-border-default">
              <th className="w-48 p-3 align-top font-normal"><span>{ui[fieldPath('', key)]?.label || key}</span><code className="block text-xs text-text-muted">{key}</code></th>
              <td className="p-3 align-top"><FieldValue present={own(data, key)} value={data[key]} schema={node} path={fieldPath('', key)} ui={ui} /></td>
            </tr>)}
            {extra.map((key) => <tr key={key} className="border-t border-border-default"><th className="p-3 align-top font-normal">{key}（额外返回）</th><td className="p-3"><JsonValue value={data[key]} /></td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ExtractResultView({ data, view }: ExtractResultViewProps) {
  const [mode, setMode] = useState<'fields' | 'json'>('fields')
  const available = view?.status === 'available'
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2" role="tablist" aria-label="结果展示方式">
        <Button role="tab" size="sm" variant={mode === 'fields' && available ? 'default' : 'secondary'} aria-selected={mode === 'fields' && available} disabled={!available} onClick={() => setMode('fields')}>字段</Button>
        <Button role="tab" size="sm" variant={mode === 'json' || !available ? 'default' : 'secondary'} aria-selected={mode === 'json' || !available} onClick={() => setMode('json')}>原始 JSON</Button>
      </div>
      {!available && <p className="text-sm text-text-muted">本次执行的展示契约不可用，显示原始结果；不会使用当前配置解释旧结果。</p>}
      {mode === 'json' || !available ? <JsonValue value={data} /> : (
        <>
          <p className="text-xs text-text-muted">展示结构来自{view.origin === 'revision' ? '本次任务固定的修订' : '本次任务的执行快照'}。“未返回”只表示结果不含该字段。</p>
          {view.target === 'per_page' ? Array.isArray(data) ? data.length === 0 ? <JsonValue value={data} /> : data.map((item, index) => (
            <section key={index} className="space-y-2 rounded-xl border border-border-default p-3"><h3 className="font-semibold">页面实例 {index + 1}（执行顺序）</h3><Instance data={item} schema={view.schema} ui={view.ui} /></section>
          )) : <JsonValue value={data} /> : <Instance data={data} schema={view.schema} ui={view.ui} />}
        </>
      )}
    </div>
  )
}
