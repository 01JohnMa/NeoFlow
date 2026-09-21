import type { ExtractSchema, ExtractSchemaUi } from '../types/extractSchema'
import {
  builderType, fieldPath, newFieldSchema, orderedProperties, pruneUi, schemaAt, upsertField,
  type BuilderType,
} from './extractSchema'

/** Transient input buffers only. Never persisted and never an alternative field contract. */
export type InlineBuffers = Record<string, { key?: string; options?: string }>
export interface InlineError { path: string; input: 'key' | 'options'; message: string }
export interface SchemaDraft { schema: ExtractSchema; ui: ExtractSchemaUi }
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T
export const inside = (path: string, root: string): boolean => path === root || path.startsWith(`${root}/`)
export const objectPath = (path: string, node: ExtractSchema): string => node.type === 'array' ? `${path}/items` : path
export const childObject = (node: ExtractSchema): ExtractSchema | undefined =>
  node.type === 'object' ? node : node.type === 'array' && node.items?.type === 'object' ? node.items : undefined

export function enumOptions(text: string): string[] {
  const values = text.replace(/\r\n/g, '\n').split('\n')
  // A final line terminator is not an additional candidate. Interior empty lines are errors.
  if (values[values.length - 1] === '') values.pop()
  return values
}

export function inlineErrors(schema: ExtractSchema, buffers: InlineBuffers): InlineError[] {
  const errors: InlineError[] = []
  function visit(node: ExtractSchema, parent: string): void {
    const names = new Map<string, number>()
    const entries = Object.entries(node.properties ?? {})
    for (const [key] of entries) {
      const name = buffers[fieldPath(parent, key)]?.key ?? key
      names.set(name, (names.get(name) ?? 0) + 1)
    }
    for (const [key, field] of entries) {
      const path = fieldPath(parent, key)
      const name = buffers[path]?.key ?? key
      if (!name.trim() || name !== name.trim()) errors.push({ path, input: 'key', message: '键名不能为空或包含首尾空白' })
      else if (names.get(name)! > 1) errors.push({ path, input: 'key', message: `同级键名重复：${name}` })
      if (builderType(field) === 'enum') {
        const options = buffers[path]?.options === undefined ? field.enum! : enumOptions(buffers[path].options!)
        if (!options.length || options.some((v) => typeof v !== 'string' || !v.trim() || /[\r\n]/.test(v))) {
          errors.push({ path, input: 'options', message: '至少填写一个候选值，不能有空项' })
        } else if (new Set(options).size !== options.length) {
          errors.push({ path, input: 'options', message: '候选值不能重复' })
        }
      }
      const object = childObject(field)
      if (object) visit(object, objectPath(path, field))
    }
  }
  visit(schema, '')
  return errors
}

/** Apply simultaneous renames atomically, including parent/child renames and sibling swaps. */
export function materializeDraft(schema: ExtractSchema, ui: ExtractSchemaUi, buffers: InlineBuffers) {
  const errors = inlineErrors(schema, buffers)
  if (errors.length) throw new Error(errors[0].message)
  const paths: Record<string, string> = {}
  function visit(node: ExtractSchema, oldPath: string, nextPath: string): ExtractSchema {
    const next = copy(node)
    if (buffers[oldPath]?.options !== undefined) next.enum = enumOptions(buffers[oldPath].options!)
    if (node.properties) {
      const rename = (key: string) => buffers[fieldPath(oldPath, key)]?.key ?? key
      next.properties = Object.fromEntries(Object.entries(node.properties).map(([key, field]) => {
        const old = fieldPath(oldPath, key)
        const path = fieldPath(nextPath, rename(key))
        paths[old] = path
        return [rename(key), visit(field, old, path)]
      }))
      if (node.required) next.required = node.required.map(rename)
    }
    if (node.items) next.items = visit(node.items, `${oldPath}/items`, `${nextPath}/items`)
    return next
  }
  const nextSchema = visit(schema, '', '')
  const nextUi = Object.fromEntries(Object.entries(ui).map(([path, metadata]) => [paths[path] ?? path, copy(metadata)]))
  return { schema: nextSchema, ui: pruneUi(nextSchema, nextUi), paths }
}

export function insertField(
  draft: SchemaDraft, parent: string, kind: BuilderType, after: string | null = null,
  buffers: InlineBuffers = {}, source?: string,
) {
  const object = schemaAt(draft.schema, parent)
  const entries = orderedProperties(object, draft.ui, parent)
  const taken = new Set(entries.flatMap(([key]) => [key, buffers[fieldPath(parent, key)]?.key ?? key]))
  const base = source ? `${buffers[fieldPath(parent, source)]?.key || source}_copy` : 'field'
  let key = source ? base : `${base}_1`
  for (let i = 2; taken.has(key); i++) key = `${base}_${i}`
  const node = source ? copy(object.properties![source]) : newFieldSchema(kind)
  const path = fieldPath(parent, key)
  const sourcePath = source ? fieldPath(parent, source) : null
  const next = upsertField(draft.schema, draft.ui, parent, null, key, node,
    sourcePath ? `${draft.ui[sourcePath]?.label || source} 副本` : '',
    !!source && !!object.required?.includes(source))
  if (sourcePath) {
    for (const [p, metadata] of Object.entries(draft.ui)) {
      if (p.startsWith(`${sourcePath}/`)) next.ui[path + p.slice(sourcePath.length)] = copy(metadata)
    }
  }
  const order = entries.map(([name]) => name)
  const index = after === null ? order.length : order.indexOf(after) + 1
  order.splice(index, 0, key)
  order.forEach((name, position) => {
    const p = fieldPath(parent, name)
    next.ui[p] = { ...next.ui[p], order: position }
  })
  const nextBuffers = { ...buffers }
  if (sourcePath) for (const [p, value] of Object.entries(buffers)) {
    if (inside(p, sourcePath)) {
      const buffer = { ...value }
      if (p === sourcePath) delete buffer.key
      nextBuffers[path + p.slice(sourcePath.length)] = buffer
    }
  }
  return { ...next, buffers: nextBuffers, key, path }
}

export function changeFieldType(draft: SchemaDraft, parent: string, key: string, kind: BuilderType, buffers: InlineBuffers) {
  const path = fieldPath(parent, key)
  const original = schemaAt(draft.schema, path)
  const oldObject = childObject(original)
  let node = newFieldSchema(kind)
  if (oldObject && childObject(node)) {
    const children = copy(oldObject)
    if (kind === 'object-list') {
      node.items = children
      if (original.type === 'object') delete children.description
    } else node = children
  }
  const descriptions = [original.description, node.description].filter((s, i, all) => s !== undefined && all.indexOf(s) === i)
  if (descriptions.length) node.description = descriptions.join('\n')
  const oldPrefix = `${objectPath(path, original)}/properties/`
  const nextPrefix = `${objectPath(path, node)}/properties/`
  const remap = (p: string): string => p.startsWith(oldPrefix) ? nextPrefix + p.slice(oldPrefix.length) : p
  const ui = Object.fromEntries(Object.entries(draft.ui).map(([p, m]) => [remap(p), m]))
  const next = upsertField(draft.schema, ui, parent, key, key, node, draft.ui[path]?.label ?? '',
    !!schemaAt(draft.schema, parent).required?.includes(key))
  next.ui[path] = { ...draft.ui[path] }
  const nextBuffers = Object.fromEntries(Object.entries(buffers)
    .filter(([p]) => !inside(p, path) || p === path || !!childObject(node))
    .map(([p, b]) => [remap(p), p === path ? { key: b.key } : b]))
  return { ...next, buffers: nextBuffers, remap }
}
