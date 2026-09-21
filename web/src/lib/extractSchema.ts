import type { ExtractSchema, ExtractSchemaUi } from '../types/extractSchema'

export type BuilderType = 'text' | 'date' | 'number' | 'boolean' | 'enum' | 'object-list'
export const BUILDER_TYPES: Record<BuilderType, string> = {
  text: '文本', date: '日期', number: '数值', boolean: '布尔', enum: '枚举', 'object-list': '对象列表',
}
export const own = (value: object, key: string): boolean =>
  Object.prototype.hasOwnProperty.call(value, key)
export const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
export const pointerToken = (key: string): string => key.replace(/~/g, '~0').replace(/\//g, '~1')
export const fieldPath = (parent: string, key: string): string =>
  `${parent}/properties/${pointerToken(key)}`
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T

export function schemaAt(schema: ExtractSchema, path: string): ExtractSchema {
  let node: unknown = schema
  for (const token of path ? path.slice(1).split('/') : []) {
    const key = token.replace(/~1/g, '/').replace(/~0/g, '~')
    if (!isRecord(node) || !own(node, key)) throw new Error(`Schema 路径不存在：${path}`)
    node = node[key]
  }
  if (!isRecord(node)) throw new Error(`不是 Schema 节点：${path}`)
  return node as ExtractSchema
}

function replaceAt(schema: ExtractSchema, path: string, node: ExtractSchema): ExtractSchema {
  if (!path) return clone(node)
  const result = clone(schema)
  const split = path.lastIndexOf('/')
  const parent = schemaAt(result, path.slice(0, split))
  const key = path.slice(split + 1).replace(/~1/g, '/').replace(/~0/g, '~')
  Object.defineProperty(parent, key, { value: clone(node), enumerable: true, writable: true, configurable: true })
  return result
}

export function orderedProperties(
  schema: ExtractSchema, ui: ExtractSchemaUi, parent = '',
): [string, ExtractSchema][] {
  const order = (key: string) => {
    const value = ui[fieldPath(parent, key)]?.order
    return typeof value === 'number' && Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER
  }
  return Object.entries(schema.properties ?? {}).sort(([a], [b]) =>
    order(a) - order(b) || (a < b ? -1 : a > b ? 1 : 0),
  )
}

export function builderType(node: ExtractSchema): BuilderType | undefined {
  if (node.type === 'array' && node.items?.type === 'object') return 'object-list'
  if (node.type === 'string') {
    if (node.enum) return 'enum'
    return node.format === 'date' ? 'date' : 'text'
  }
  if (node.type === 'number' || node.type === 'boolean') return node.type
  return undefined
}

/** A capability check, not an alternative JSON Schema validator/compiler. */
export function builderIssue(schema: ExtractSchema): string | null {
  function objectIssue(node: ExtractSchema, path: string, allowLists: boolean): string | null {
    if (!isRecord(node) || node.type !== 'object' || !isRecord(node.properties)) return `${path || '/'}：需要对象及 properties`
    const extra = Object.keys(node).find((key) => !['type', 'properties', 'required', 'description', 'additionalProperties'].includes(key))
    if (extra) return `${path || '/'}：请在 JSON 视图编辑 ${extra}`
    if (node.required?.some((key) => !own(node.properties!, key))) return `${path || '/'}：required 引用了未声明字段`
    for (const [key, field] of Object.entries(node.properties)) {
      const child = fieldPath(path, key)
      if (!isRecord(field)) return `${child}：Schema 节点必须是对象`
      const kind = builderType(field)
      if (!kind) return `${child}：该结构请在 JSON 视图编辑`
      if (kind === 'object-list') {
        if (!allowLists) return `${child}：Builder 不支持继续嵌套列表`
        const unsupported = Object.keys(field).find((name) => !['type', 'items', 'description'].includes(name))
        if (unsupported) return `${child}：请在 JSON 视图编辑 ${unsupported}`
        const issue = objectIssue(field.items!, `${child}/items`, false)
        if (issue) return issue
      } else {
        const allowed = ['type', 'description', ...(kind === 'date' ? ['format'] : []), ...(kind === 'enum' ? ['enum'] : [])]
        const unsupported = Object.keys(field).find((name) => !allowed.includes(name))
        if (unsupported) return `${child}：请在 JSON 视图编辑 ${unsupported}`
        if (kind === 'enum' && (!field.enum?.length || field.enum.some((item) => typeof item !== 'string' || !item.trim() || /[\r\n]/.test(item)))) {
          return `${child}：Builder 只编辑非空字符串枚举`
        }
      }
    }
    return null
  }
  return objectIssue(schema, '', true)
}

export function newFieldSchema(kind: BuilderType): ExtractSchema {
  if (kind === 'object-list') return {
    type: 'array', items: { type: 'object', properties: {}, additionalProperties: false },
  }
  if (kind === 'enum') return { type: 'string', enum: [] }
  if (kind === 'date') return { type: 'string', format: 'date' }
  return { type: kind === 'text' ? 'string' : kind }
}

export function pruneUi(schema: ExtractSchema, ui: ExtractSchemaUi): ExtractSchemaUi {
  const paths = new Set<string>()
  const visit = (node: ExtractSchema, path: string) => {
    if (!isRecord(node)) return
    for (const [key, child] of Object.entries(isRecord(node.properties) ? node.properties : {})) {
      const next = fieldPath(path, key)
      paths.add(next)
      visit(child, next)
    }
    if (node.items) visit(node.items, `${path}/items`)
  }
  visit(schema, '')
  return Object.fromEntries(Object.entries(ui).filter(([path]) => paths.has(path)))
}

export function upsertField(
  schema: ExtractSchema, ui: ExtractSchemaUi, parent: string, oldKey: string | null,
  key: string, node: ExtractSchema, label: string, required: boolean,
): { schema: ExtractSchema; ui: ExtractSchemaUi } {
  if (!key.trim() || key !== key.trim()) throw new Error('字段键名不能为空或包含首尾空白')
  const object = schemaAt(schema, parent)
  const properties = object.properties ?? {}
  if (object.type !== 'object') throw new Error('字段必须属于对象')
  if (oldKey !== null && !own(properties, oldKey)) throw new Error('待编辑字段不存在')
  if (key !== oldKey && own(properties, key)) throw new Error(`同级字段键名重复：${key}`)
  const entries = Object.entries(properties).map(([name, value]): [string, ExtractSchema] =>
    name === oldKey ? [key, node] : [name, value],
  )
  if (oldKey === null) entries.push([key, node])
  const nextObject = { ...object, properties: Object.fromEntries(entries) }
  const requiredKeys = new Set((object.required ?? []).map((name) => name === oldKey ? key : name))
  if (required) requiredKeys.add(key)
  else requiredKeys.delete(key)
  if (requiredKeys.size) nextObject.required = [...requiredKeys]
  else delete nextObject.required
  const nextSchema = replaceAt(schema, parent, nextObject)
  const path = fieldPath(parent, key)
  const oldPath = oldKey === null ? null : fieldPath(parent, oldKey)
  const nextUi = Object.fromEntries(Object.entries(ui).map(([p, metadata]) => [
    oldPath && (p === oldPath || p.startsWith(`${oldPath}/`)) ? path + p.slice(oldPath.length) : p,
    metadata,
  ])) as ExtractSchemaUi
  const lastOrder = Math.max(-1, ...orderedProperties(object, ui, parent).map(([name], index) =>
    ui[fieldPath(parent, name)]?.order ?? index,
  ))
  nextUi[path] = { ...nextUi[path], label, order: nextUi[path]?.order ?? lastOrder + 1 }
  return { schema: nextSchema, ui: pruneUi(nextSchema, nextUi) }
}

export function removeField(
  schema: ExtractSchema, ui: ExtractSchemaUi, parent: string, key: string,
): { schema: ExtractSchema; ui: ExtractSchemaUi } {
  const object = schemaAt(schema, parent)
  if (!own(object.properties ?? {}, key)) throw new Error('待删除字段不存在')
  const next = { ...object, properties: Object.fromEntries(Object.entries(object.properties!).filter(([name]) => name !== key)) }
  if (object.required) next.required = object.required.filter((name) => name !== key)
  const nextSchema = replaceAt(schema, parent, next)
  return { schema: nextSchema, ui: pruneUi(nextSchema, ui) }
}

export function moveField(
  schema: ExtractSchema, ui: ExtractSchemaUi, parent: string, key: string, direction: -1 | 1,
): ExtractSchemaUi {
  const entries = orderedProperties(schemaAt(schema, parent), ui, parent)
  const index = entries.findIndex(([name]) => name === key)
  const next = index + direction
  if (index < 0 || next < 0 || next >= entries.length) return ui
  ;[entries[index], entries[next]] = [entries[next], entries[index]]
  return { ...ui, ...Object.fromEntries(entries.map(([name], order) => {
    const path = fieldPath(parent, name)
    return [path, { ...ui[path], order }]
  })) }
}

/** Parse without silently accepting duplicate object keys (including escaped aliases). */
export function parseSchemaJson(text: string): ExtractSchema {
  const value: unknown = JSON.parse(text)
  if (!isRecord(value)) throw new Error('Schema 必须是 JSON 对象')
  const tokens = text.match(/"(?:\\.|[^"\\])*"|true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|[{}\[\]:,]/g) ?? []
  let cursor = 0
  function scan(depth: number): void {
    if (depth > 100) throw new Error('JSON 嵌套过深')
    const token = tokens[cursor++]
    if (token === '{') {
      const names = new Set<string>()
      if (tokens[cursor] !== '}') do {
        const name = JSON.parse(tokens[cursor++]) as string
        if (names.has(name)) throw new Error(`JSON 对象存在重复键：${name}`)
        names.add(name)
        cursor++ // colon; syntax was already checked by JSON.parse.
        scan(depth + 1)
        if (tokens[cursor] !== ',') break
        cursor++
      } while (true)
      cursor++ // }
    } else if (token === '[') {
      if (tokens[cursor] !== ']') do {
        scan(depth + 1)
        if (tokens[cursor] !== ',') break
        cursor++
      } while (true)
      cursor++ // ]
    }
  }
  scan(0)
  return value as ExtractSchema
}
