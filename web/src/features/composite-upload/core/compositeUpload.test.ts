import { describe, expect, it } from 'vitest'
import {
  buildCompositeBatchPayload,
  createEmptyCompositeGroup,
  createEmptyCompositeGroupSeededFromFirst,
  getDefaultCompositeGroupPushName,
  getSubmittableCompositeGroups,
  getSubmittableCompositeUploadFiles,
  getUploadedFileIdentity,
  isCompositeFileUsedInOtherGroups,
  summarizeCompositeGroups,
  validateCompositeGroups,
} from '@/features/composite-upload/core/compositeUpload'
import type {
  CompositeGroup,
  CompositeScenarioConfig,
  CompositeUploadedFile,
} from '@/features/composite-upload/core/types'

function createFile(id: string, name: string): CompositeUploadedFile {
  return {
    id,
    file: new File(['demo'], name, {
      type: 'application/pdf',
      lastModified: 1710000000000,
    }),
    preview: null,
  }
}

function createNativeFile(name: string, lastModified: number = 1710000000000): File {
  return new File(['demo'], name, {
    type: 'application/pdf',
    lastModified,
  })
}

function createGroup(
  id: string,
  options?: {
    documents?: Partial<Record<'slotA' | 'slotB', CompositeUploadedFile>>
    templateSelections?: Partial<Record<'slotA' | 'slotB', string | null>>
  },
): CompositeGroup {
  return {
    id,
    documents: {
      slotA: options?.documents?.slotA ?? null,
      slotB: options?.documents?.slotB ?? null,
    },
    templateSelections: {
      slotA: options?.templateSelections?.slotA ?? null,
      slotB: options?.templateSelections?.slotB ?? null,
    },
  }
}

function createScenario(overrides?: Partial<CompositeScenarioConfig>): CompositeScenarioConfig {
  return {
    scenarioKey: 'generic_batch',
    displayName: '批量处理',
    description: '按组上传文档',
    enabled: true,
    maxGroups: 5,
    slotDefinitions: [
      {
        slotKey: 'slotA',
        label: '文档 A',
        required: false,
      },
      {
        slotKey: 'slotB',
        label: '文档 B',
        required: false,
      },
    ],
    templateOptions: [
      { id: 'tpl-a', name: '模板 A', code: 'template_a' },
      { id: 'tpl-b', name: '模板 B', code: 'template_b' },
      { id: 'tpl-c', name: '模板 C', code: 'template_c' },
    ],
    pushNameStrategy: 'slotB-first',
    ...overrides,
  }
}

describe('composite upload core', () => {
  it('创建空分组时包含场景定义的全部槽位和模板选择状态', () => {
    const scenario = createScenario()

    expect(createEmptyCompositeGroup(scenario)).toEqual({
      id: expect.stringMatching(/^composite-group-/),
      documents: {
        slotA: null,
        slotB: null,
      },
      templateSelections: {
        slotA: null,
        slotB: null,
      },
    })
  })

  it('新增分组时从第一组复制各槽位的文档类型选择', () => {
    const scenario = createScenario()
    const first = createGroup('g1', {
      templateSelections: { slotA: 'tpl-a', slotB: 'tpl-b' },
    })
    const seeded = createEmptyCompositeGroupSeededFromFirst(scenario, first)

    expect(seeded.templateSelections).toEqual({
      slotA: 'tpl-a',
      slotB: 'tpl-b',
    })
    expect(seeded.documents).toEqual({
      slotA: null,
      slotB: null,
    })
  })

  it('按场景策略汇总分组状态与任务总数', () => {
    const scenario = createScenario()
    const groups = [
      createGroup('g1', {
        documents: { slotA: createFile('a1', '文档A1.pdf'), slotB: createFile('b1', '文档B1.pdf') },
        templateSelections: { slotA: 'tpl-a', slotB: 'tpl-b' },
      }),
      createGroup('g2', {
        documents: { slotA: createFile('a2', '文档A2.pdf') },
        templateSelections: { slotA: 'tpl-c' },
      }),
      createGroup('g3', { documents: { slotB: createFile('b3', '文档B3.pdf') } }),
      createGroup('g4'),
    ]

    expect(summarizeCompositeGroups(groups, scenario)).toEqual({
      empty: 1,
      complete: 1,
      partial: 2,
      totalTasks: 3,
    })
  })

  it('文件已上传但未选择模板时返回分组级校验错误', () => {
    const scenario = createScenario()
    const groups = [
      createGroup('g1', {
        documents: { slotA: createFile('a1', '文档A1.pdf'), slotB: createFile('b1', '文档B1.pdf') },
        templateSelections: { slotA: 'tpl-a' },
      }),
    ]

    const result = validateCompositeGroups(groups, scenario)

    expect(result.canSubmit).toBe(false)
    expect(result.groupErrors.g1).toContain('请为“文档 B”选择文档类型后再提交')
  })

  it('根据组内已选择模板构建 single 与 merge 批处理项，并按组映射推送名', () => {
    const scenario = createScenario()
    const groups = [
      createGroup('g1', {
        documents: { slotA: createFile('a1', '文档A1.pdf'), slotB: createFile('b1', '文档B1.pdf') },
        templateSelections: { slotA: 'tpl-a', slotB: 'tpl-b' },
      }),
      createGroup('g2', {
        documents: { slotB: createFile('b2', '文档B2.pdf') },
        templateSelections: { slotB: 'tpl-c' },
      }),
    ]

    const result = buildCompositeBatchPayload({
      groups,
      scenario,
      uploadResults: {
        a1: { document_id: 'doc-a1', file_path: '/doc-a1' },
        b1: { document_id: 'doc-b1', file_path: '/doc-b1' },
        b2: { document_id: 'doc-b2', file_path: '/doc-b2' },
      },
      groupCustomPushNames: {
        g1: '组一推送名',
        g2: '组二推送名',
      },
    })

    expect(result.items).toEqual([
      {
        document_id: 'doc-a1',
        template_id: 'tpl-a',
        paired_document_id: 'doc-b1',
        paired_template_id: 'tpl-b',
        custom_push_name: '组一推送名',
      },
      {
        document_id: 'doc-b2',
        template_id: 'tpl-c',
        custom_push_name: '组二推送名',
      },
    ])
    expect(result.fileCustomPushNameMap).toEqual({
      a1: '组一推送名',
      b1: '组一推送名',
      b2: '组二推送名',
    })
  })

  it('按场景策略优先使用 slotB 作为推荐推送名', () => {
    const scenario = createScenario()

    expect(getDefaultCompositeGroupPushName(createGroup('g1', {
      documents: {
        slotA: createFile('a1', '文档A.pdf'),
        slotB: createFile('b1', '文档B.pdf'),
      },
      templateSelections: { slotA: 'tpl-a', slotB: 'tpl-b' },
    }), scenario)).toBe('文档B')

    expect(getDefaultCompositeGroupPushName(createGroup('g2', {
      documents: { slotA: createFile('a2', '仅文档A.pdf') },
      templateSelections: { slotA: 'tpl-a' },
    }), scenario)).toBe('仅文档A')
  })

  it('检测跨分组重复文件占用', () => {
    const duplicatedFile = createNativeFile('重复文件.pdf')
    const groups = [
      createGroup('g1', {
        documents: { slotA: { id: 'f1', file: duplicatedFile, preview: null } },
        templateSelections: { slotA: 'tpl-a' },
      }),
      createGroup('g2'),
    ]

    expect(isCompositeFileUsedInOtherGroups(groups, 'g2', createNativeFile('重复文件.pdf'))).toBe(true)
    expect(isCompositeFileUsedInOtherGroups(groups, 'g1', createNativeFile('重复文件.pdf'))).toBe(false)
    expect(getUploadedFileIdentity(groups[0].documents.slotA!)).toContain('重复文件.pdf')
  })

  it('仅返回可提交分组涉及的文件', () => {
    const scenario = createScenario()
    const groups = [
      createGroup('g1', {
        documents: { slotA: createFile('a1', '文档A1.pdf'), slotB: createFile('b1', '文档B1.pdf') },
        templateSelections: { slotA: 'tpl-a', slotB: 'tpl-b' },
      }),
      createGroup('g2', {
        documents: { slotB: createFile('b2', '文档B2.pdf') },
        templateSelections: { slotB: 'tpl-c' },
      }),
      createGroup('g3', {
        documents: { slotA: createFile('a3', '文档A3.pdf') },
      }),
    ]

    expect(getSubmittableCompositeGroups(groups, scenario).map(group => group.id)).toEqual(['g1', 'g2'])
    expect(getSubmittableCompositeUploadFiles(groups, scenario).map(file => file.id)).toEqual(['a1', 'b1', 'b2'])
  })
})
