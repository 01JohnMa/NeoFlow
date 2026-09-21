import { describe, expect, it } from 'vitest'
import {
  builderIssue, fieldPath, moveField, orderedProperties, parseSchemaJson,
  removeField, upsertField,
} from './extractSchema'
import type { ExtractSchema, ExtractSchemaUi } from '../types/extractSchema'

const schema: ExtractSchema = { type: 'object', properties: {
  products: { type: 'array', items: { type: 'object', properties: {
    name: { type: 'string' }, enabled: { type: 'boolean' },
  }, required: ['name'], additionalProperties: false } },
  n: { type: 'number' },
}, additionalProperties: false }
const ui: ExtractSchemaUi = {
  '/properties/products': { label: '产品', order: 0 },
  '/properties/n': { label: '数值', order: 1 },
  '/properties/products/items/properties/name': { label: '名称', order: 0 },
}

describe('schema-first editing', () => {
  it('edits object lists but not arbitrary nested Builder nodes', () => {
    expect(builderIssue(schema)).toBeNull()
    expect(builderIssue({ type: 'object', properties: { n: { type: 'integer' } } })).toBeTruthy()
  })
  it('does not mutate input when renaming a required child', () => {
    const before = JSON.stringify([schema, ui])
    const next = upsertField(schema, ui, '/properties/products/items', 'name', 'title', { type: 'string' }, '标题', true)
    expect(next.schema.properties!.products.items!.required).toEqual(['title'])
    expect(next.ui['/properties/products/items/properties/title'].label).toBe('标题')
    expect(next.ui['/properties/products/items/properties/name']).toBeUndefined()
    expect(JSON.stringify([schema, ui])).toBe(before)
    expect(next.schema.required).toBeUndefined()
  })
  it('renames a container and all descendant display pointers', () => {
    const next = upsertField(schema, ui, '', 'products', 'items', schema.properties!.products, '项目', false)
    expect(next.ui['/properties/items/items/properties/name'].label).toBe('名称')
    expect(next.ui['/properties/products/items/properties/name']).toBeUndefined()
  })
  it('rejects duplicate keys before object construction', () => {
    expect(() => upsertField(schema, ui, '', null, 'n', { type: 'string' }, 'x', false)).toThrow('重复')
  })
  it('deleting a container removes descendant metadata without changing other fields', () => {
    const next = removeField(schema, ui, '', 'products')
    expect(Object.keys(next.schema.properties!)).toEqual(['n'])
    expect(Object.keys(next.ui)).toEqual(['/properties/n'])
  })
  it('display order never changes the extraction schema', () => {
    const before = JSON.stringify(schema)
    const nextUi = moveField(schema, ui, '', 'n', -1)
    expect(orderedProperties(schema, nextUi).map(([key]) => key)).toEqual(['n', 'products'])
    expect(JSON.stringify(schema)).toBe(before)
  })
  it('handles pointer escaping and special object property names safely', () => {
    expect(fieldPath('', 'a/~b')).toBe('/properties/a~1~0b')
    const next = upsertField(schema, ui, '', null, '__proto__', { type: 'boolean' }, '特殊键', false)
    expect(Object.keys(next.schema.properties!)).toContain('__proto__')
    expect(Object.getPrototypeOf(next.schema.properties)).toBe(Object.prototype)
  })
  it('refuses duplicate JSON keys including escaped aliases and nested objects', () => {
    expect(() => parseSchemaJson('{"type":"object","type":"array"}')).toThrow('重复')
    expect(() => parseSchemaJson('{"properties":{"a":{},"\\u0061":{}}}')).toThrow('重复')
    expect(() => parseSchemaJson('{"enum":[{"a":1,"a":2}]}')).toThrow('重复')
  })
  it('raw JSON retains union types and non-string enum values losslessly', () => {
    const raw = '{"type":"object","properties":{"v":{"type":["integer","null"],"enum":[1,null]}}}'
    expect(JSON.stringify(parseSchemaJson(raw))).toBe(raw)
  })
})
