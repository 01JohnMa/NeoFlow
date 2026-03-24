import { describe, expect, it } from 'vitest'
import type { Template } from '@/store/useStore'
import { resolveSelectedSingleTemplateId } from './singleUploadState'

function createTemplate(partial: Partial<Template>): Template {
  return {
    id: partial.id || 'tpl-id',
    name: partial.name || '模板',
    code: partial.code || 'template_code',
    required_doc_count: partial.required_doc_count || 1,
    is_active: partial.is_active ?? true,
    description: partial.description,
  }
}

describe('singleUploadState', () => {
  it('单模板场景自动选中唯一模板', () => {
    const templates = [createTemplate({ id: 'tpl-1' })]

    expect(resolveSelectedSingleTemplateId(templates, null)).toBe('tpl-1')
  })

  it('多模板场景未显式选择时不应自动回退到第一个模板', () => {
    const templates = [createTemplate({ id: 'tpl-1' }), createTemplate({ id: 'tpl-2' })]

    expect(resolveSelectedSingleTemplateId(templates, null)).toBeNull()
  })

  it('多模板场景保留用户显式选择的模板', () => {
    const templates = [createTemplate({ id: 'tpl-1' }), createTemplate({ id: 'tpl-2' })]

    expect(resolveSelectedSingleTemplateId(templates, 'tpl-2')).toBe('tpl-2')
  })
})
