import { describe, expect, it } from 'vitest'
import {
  buildCompositeBatchPayload,
  createEmptyCompositeGroup,
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

function createGroup(id: string, documents?: Partial<Record<'slotA' | 'slotB', CompositeUploadedFile>>): CompositeGroup {
  return {
    id,
    documents: {
      slotA: documents?.slotA ?? null,
      slotB: documents?.slotB ?? null,
    },
  }
}

function createScenario(overrides?: Partial<CompositeScenarioConfig>): CompositeScenarioConfig {
  return {
    scenarioKey: 'lighting_pair',
    displayName: '照明分组上传',
    description: '按组上传双文档',
    enabled: true,
    maxGroups: 5,
    slotDefinitions: [
      {
        slotKey: 'slotA',
        label: '积分球',
        templateCode: 'integrating_sphere',
        templateId: 'sphere-tpl',
        required: false,
      },
      {
        slotKey: 'slotB',
        label: '光分布',
        templateCode: 'light_distribution',
        templateId: 'distribution-tpl',
        required: false,
      },
    ],
    pushNameStrategy: 'slotB-first',
    ...overrides,
  }
}

describe('composite upload core', () => {
  it('创建空分组时包含场景定义的全部槽位', () => {
    const scenario = createScenario()

    expect(createEmptyCompositeGroup(scenario)).toEqual({
      id: expect.stringMatching(/^composite-group-/),
      documents: {
        slotA: null,
        slotB: null,
      },
    })
  })

  it('按场景策略汇总分组状态与任务总数', () => {
    const scenario = createScenario()
    const groups = [
      createGroup('g1', { slotA: createFile('a1', '积分球A.pdf'), slotB: createFile('b1', '光分布A.pdf') }),
      createGroup('g2', { slotA: createFile('a2', '积分球B.pdf') }),
      createGroup('g3', { slotB: createFile('b3', '光分布C.pdf') }),
      createGroup('g4'),
    ]

    expect(summarizeCompositeGroups(groups, scenario)).toEqual({
      empty: 1,
      complete: 1,
      partial: 2,
      totalTasks: 3,
    })
  })

  it('缺少槽位模板时返回分组级校验错误', () => {
    const scenario = createScenario({
      slotDefinitions: [
        {
          slotKey: 'slotA',
          label: '积分球',
          templateCode: 'integrating_sphere',
          templateId: 'sphere-tpl',
          required: false,
        },
      ],
    })
    const groups = [createGroup('g1', { slotA: createFile('a1', '积分球A.pdf'), slotB: createFile('b1', '光分布A.pdf') })]

    const result = validateCompositeGroups(groups, scenario)

    expect(result.canSubmit).toBe(false)
    expect(result.groupErrors.g1).toContain('缺少“slotB”对应模板，当前分组无法提交该槽位文件')
  })

  it('根据已上传文档构建 single 与 merge 批处理项，并按组映射推送名', () => {
    const scenario = createScenario()
    const groups = [
      createGroup('g1', { slotA: createFile('a1', '积分球A.pdf'), slotB: createFile('b1', '光分布A.pdf') }),
      createGroup('g2', { slotB: createFile('b2', '光分布B.pdf') }),
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
        template_id: 'sphere-tpl',
        paired_document_id: 'doc-b1',
        paired_template_id: 'distribution-tpl',
        custom_push_name: '组一推送名',
      },
      {
        document_id: 'doc-b2',
        template_id: 'distribution-tpl',
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
      slotA: createFile('a1', '积分球文件.pdf'),
      slotB: createFile('b1', '光分布文件.pdf'),
    }), scenario)).toBe('光分布文件')

    expect(getDefaultCompositeGroupPushName(createGroup('g2', {
      slotA: createFile('a2', '仅积分球文件.pdf'),
    }), scenario)).toBe('仅积分球文件')
  })

  it('检测跨分组重复文件占用', () => {
    const duplicatedFile = createNativeFile('重复文件.pdf')
    const groups = [
      createGroup('g1', { slotA: { id: 'f1', file: duplicatedFile, preview: null } }),
      createGroup('g2'),
    ]

    expect(isCompositeFileUsedInOtherGroups(groups, 'g2', createNativeFile('重复文件.pdf'))).toBe(true)
    expect(isCompositeFileUsedInOtherGroups(groups, 'g1', createNativeFile('重复文件.pdf'))).toBe(false)
    expect(getUploadedFileIdentity(groups[0].documents.slotA!)).toContain('重复文件.pdf')
  })

  it('仅返回可提交分组涉及的文件', () => {
    const scenario = createScenario()
    const groups = [
      createGroup('g1', { slotA: createFile('a1', '积分球A.pdf'), slotB: createFile('b1', '光分布A.pdf') }),
      createGroup('g2', { slotB: createFile('b2', '光分布B.pdf') }),
      createGroup('g3'),
    ]

    expect(getSubmittableCompositeGroups(groups, scenario).map(group => group.id)).toEqual(['g1', 'g2'])
    expect(getSubmittableCompositeUploadFiles(groups, scenario).map(file => file.id)).toEqual(['a1', 'b1', 'b2'])
  })
})
