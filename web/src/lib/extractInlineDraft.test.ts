import { describe, expect, it } from 'vitest'
import { builderIssue, fieldPath, orderedProperties, schemaAt } from './extractSchema'
import { changeFieldType, inlineErrors, insertField, materializeDraft } from './extractInlineDraft'
import type { ExtractSchema, ExtractSchemaUi } from '../types/extractSchema'

const schema: ExtractSchema = { type: 'object', properties: {
  products: { type: 'array', description: '产品', items: { type: 'object', properties: {
    name: { type: 'string' }, form: { type: 'string', enum: ['片剂', '胶囊'] },
  }, required: ['name'], additionalProperties: false } },
  other: { type: 'string' },
}, additionalProperties: false }
const ui: ExtractSchemaUi = {
  '/properties/products': { label: '产品', order: 0 }, '/properties/other': { order: 1 },
  '/properties/products/items/properties/name': { label: '名称', order: 0 },
}

describe('inline schema draft', () => {
  it('atomically renames parents and required children with escaped pointers', () => {
    const before = JSON.stringify([schema, ui])
    const next = materializeDraft(schema, ui, {
      '/properties/products': { key: 'a/~b' },
      '/properties/products/items/properties/name': { key: 'title' },
    })
    expect(next.schema.properties!['a/~b'].items!.required).toEqual(['title'])
    expect(next.schema.required).toBeUndefined()
    expect(next.ui['/properties/a~1~0b/items/properties/title'].label).toBe('名称')
    expect(next.paths['/properties/products/items/properties/name']).toBe('/properties/a~1~0b/items/properties/title')
    expect(JSON.stringify([schema, ui])).toBe(before)
  })
  it('supports sibling name swaps without overwriting either schema', () => {
    const next = materializeDraft(schema, ui, { '/properties/products': { key: 'other' }, '/properties/other': { key: 'products' } })
    expect(next.schema.properties!.other.type).toBe('array')
    expect(next.schema.properties!.products.type).toBe('string')
  })
  it('keeps invalid input local and reports both duplicate keys', () => {
    const buffers = { '/properties/products': { key: 'other' } }
    expect(inlineErrors(schema, buffers)).toHaveLength(2)
    expect(() => materializeDraft(schema, ui, buffers)).toThrow('重复')
    expect(inlineErrors(schema, { '/properties/other': { key: ' ' } })[0].path).toBe('/properties/other')
  })
  it('preserves enum spelling, allows trailing newline, rejects empty and duplicate candidates', () => {
    const path = '/properties/products/items/properties/form'
    expect(materializeDraft(schema, ui, { [path]: { options: ' A \nB\n' } }).schema.properties!.products.items!.properties!.form.enum).toEqual([' A ', 'B'])
    for (const text of ['', 'A\n\nB', 'A\nA']) expect(inlineErrors(schema, { [path]: { options: text } })).toHaveLength(1)
  })
  it('inserts next to the requested row without rewriting schema order', () => {
    const next = insertField({ schema, ui }, '', 'object', 'products')
    expect(orderedProperties(next.schema, next.ui).map(([k]) => k)).toEqual(['products', next.key, 'other'])
    expect(builderIssue(next.schema)).toBeNull()
    expect(schemaAt(next.schema, next.path).properties).toEqual({})
  })
  it('deep-copies containers, UI, required, enums and pending child edits', () => {
    const next = insertField({ schema, ui }, '', 'object-list', 'products', {
      '/properties/products/items/properties/form': { options: 'A\nB' },
      '/properties/products/items/properties/name': { key: 'title' },
    }, 'products')
    const result = materializeDraft(next.schema, next.ui, next.buffers)
    const original = result.schema.properties!.products
    const duplicate = result.schema.properties![next.key]
    duplicate.items!.properties!.form.enum!.push('C')
    expect(original.items!.properties!.form.enum).toEqual(['A', 'B'])
    expect(duplicate.items!.required).toEqual(['title'])
    expect(result.ui[`${next.path}/items/properties/title`].label).toBe('名称')
    expect(orderedProperties(result.schema, result.ui).map(([k]) => k)).toEqual(['products', next.key, 'other'])
  })
  it('converts object/list shape while preserving children and remapping metadata/buffers', () => {
    const next = changeFieldType({ schema, ui }, '', 'products', 'object', { '/properties/products/items/properties/name': { key: 'title' } })
    expect(builderIssue(next.schema)).toBeNull()
    expect(next.ui['/properties/products/properties/name'].label).toBe('名称')
    const result = materializeDraft(next.schema, next.ui, next.buffers)
    expect(result.schema.properties!.products.required).toEqual(['title'])
    const back = changeFieldType(result, '', 'products', 'object-list', {})
    expect(back.schema.properties!.products.items!.required).toEqual(['title'])
    expect(back.ui['/properties/products/items/properties/title'].label).toBe('名称')
  })
  it('removes children and their input buffers when explicitly changing to scalar', () => {
    const next = changeFieldType({ schema, ui }, '', 'products', 'text', {
      '/properties/products': { key: 'p' }, '/properties/products/items/properties/name': { key: '' },
    })
    expect(Object.keys(next.buffers)).toEqual(['/properties/products'])
    expect(next.schema.properties!.products.items).toBeUndefined()
    expect(next.ui['/properties/products/items/properties/name']).toBeUndefined()
  })
  it('does not widen Builder to recursive objects or change required on root', () => {
    const next = insertField({ schema, ui }, '/properties/products/items', 'object')
    expect(builderIssue(next.schema)).toBeTruthy()
    expect(next.schema.required).toBeUndefined()
  })
  it('handles special property names without prototype pollution', () => {
    const next = materializeDraft(schema, ui, { '/properties/other': { key: '__proto__' } })
    expect(schemaAt(next.schema, fieldPath('', '__proto__')).type).toBe('string')
    expect(Object.getPrototypeOf(next.schema.properties)).toBe(Object.prototype)
  })
})
