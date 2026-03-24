import { describe, expect, it } from 'vitest'
import type { Template } from '@/store/useStore'
import type { LightingGroup, UploadedFile } from '@/components/BatchMergePairing'
import {
  buildLightingBatchPayload,
  getDefaultGroupPushName,
  getDefaultSinglePushName,
  getSubmittableLightingGroups,
  getSubmittableUploadFiles,
  isLightingFileUsedInOtherGroups,
  resolveEffectivePushName,
  resolveFixedLightingTemplates,
  summarizeLightingGroups,
  validateLightingGroups,
} from './uploadBatchUtils'

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

function createFile(id: string, name: string): UploadedFile {
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

function createGroup(partial: Partial<LightingGroup> & Pick<LightingGroup, 'id'>): LightingGroup {
  return {
    id: partial.id,
    sphereFile: partial.sphereFile ?? null,
    distributionFile: partial.distributionFile ?? null,
  }
}

describe('uploadBatchUtils', () => {
  it('按固定 code 自动解析照明模板', () => {
    const templates = [
      createTemplate({ id: 'sphere-tpl', code: 'integrating_sphere', name: '积分球模板' }),
      createTemplate({ id: 'distribution-tpl', code: 'light_distribution', name: '光分布模板' }),
      createTemplate({ id: 'other-tpl', code: 'other_template', name: '其他模板' }),
    ]

    const result = resolveFixedLightingTemplates(templates)

    expect(result.integratingSphereTemplate?.id).toBe('sphere-tpl')
    expect(result.lightDistributionTemplate?.id).toBe('distribution-tpl')
    expect(result.lightingTemplatesReady).toBe(true)
  })

  it('汇总分组状态与任务总数', () => {
    const groups: LightingGroup[] = [
      createGroup({ id: 'g1', sphereFile: createFile('s1', 'sphere-a.pdf'), distributionFile: createFile('d1', 'distribution-a.pdf') }),
      createGroup({ id: 'g2', sphereFile: createFile('s2', 'sphere-b.pdf') }),
      createGroup({ id: 'g3', distributionFile: createFile('d3', 'distribution-c.pdf') }),
      createGroup({ id: 'g4' }),
    ]

    const summary = summarizeLightingGroups(groups)

    expect(summary).toEqual({
      empty: 1,
      complete: 1,
      sphereOnly: 1,
      distributionOnly: 1,
      totalTasks: 3,
    })
  })

  it('在缺少固定模板时返回分组校验错误', () => {
    const groups: LightingGroup[] = [
      createGroup({ id: 'g1', sphereFile: createFile('s1', 'sphere-a.pdf'), distributionFile: createFile('d1', 'distribution-a.pdf') }),
      createGroup({ id: 'g2', distributionFile: createFile('d2', 'distribution-b.pdf') }),
    ]

    const fixedTemplates = resolveFixedLightingTemplates([
      createTemplate({ id: 'sphere-tpl', code: 'integrating_sphere' }),
    ])

    const result = validateLightingGroups(groups, fixedTemplates)

    expect(result.canSubmit).toBe(false)
    expect(result.groupErrors.g1).toContain('缺少“光分布”固定模板，当前分组无法提交光分布文件')
    expect(result.groupErrors.g2).toContain('缺少“光分布”固定模板，当前分组无法提交光分布文件')
  })

  it('根据组内文件生成 single 与 merge 批处理项，并映射组级推送名', () => {
    const sphereFile = createFile('sphere-1', '积分球样本.pdf')
    const distributionFile = createFile('distribution-1', '光分布样本.pdf')
    const distributionOnlyFile = createFile('distribution-2', '光分布单文件.pdf')
    const groups: LightingGroup[] = [
      createGroup({ id: 'g1', sphereFile, distributionFile }),
      createGroup({ id: 'g2', distributionFile: distributionOnlyFile }),
    ]
    const fixedTemplates = resolveFixedLightingTemplates([
      createTemplate({ id: 'sphere-tpl', code: 'integrating_sphere' }),
      createTemplate({ id: 'distribution-tpl', code: 'light_distribution' }),
    ])

    const result = buildLightingBatchPayload({
      groups,
      fixedTemplates,
      uploadResults: {
        'sphere-1': { document_id: 'doc-sphere-1', file_path: '/doc-sphere-1' },
        'distribution-1': { document_id: 'doc-distribution-1', file_path: '/doc-distribution-1' },
        'distribution-2': { document_id: 'doc-distribution-2', file_path: '/doc-distribution-2' },
      },
      batchCustomPushNames: {
        g1: '组一推送名',
        g2: '组二推送名',
      },
    })

    expect(result.items).toEqual([
      {
        document_id: 'doc-sphere-1',
        template_id: 'sphere-tpl',
        paired_document_id: 'doc-distribution-1',
        paired_template_id: 'distribution-tpl',
        custom_push_name: '组一推送名',
      },
      {
        document_id: 'doc-distribution-2',
        template_id: 'distribution-tpl',
        custom_push_name: '组二推送名',
      },
    ])

    expect(result.fileCustomPushNameMap).toEqual({
      'sphere-1': '组一推送名',
      'distribution-1': '组一推送名',
      'distribution-2': '组二推送名',
    })
  })

  it('优先使用光分布文件名作为默认推送文件名，没有光分布时才退回积分球', () => {
    const completeName = getDefaultGroupPushName(
      createGroup({
        id: 'g1',
        sphereFile: createFile('s1', '积分球文件.pdf'),
        distributionFile: createFile('d1', '光分布文件.pdf'),
      })
    )
    const distributionOnlyName = getDefaultGroupPushName(
      createGroup({
        id: 'g2',
        distributionFile: createFile('d2', '仅光分布文件.pdf'),
      })
    )
    const sphereOnlyName = getDefaultGroupPushName(
      createGroup({
        id: 'g3',
        sphereFile: createFile('s3', '仅积分球文件.pdf'),
      })
    )

    expect(completeName).toBe('光分布文件')
    expect(distributionOnlyName).toBe('仅光分布文件')
    expect(sphereOnlyName).toBe('仅积分球文件')
  })

  it('为单文件上传生成推荐推送文件名', () => {
    const template = createTemplate({ name: '积分球模板' })
    const file = createNativeFile('原始文件.pdf')

    expect(getDefaultSinglePushName(file, template)).toBe('原始文件')
    expect(getDefaultSinglePushName(file, null)).toBe('原始文件')
  })

  it('优先使用用户输入的文件名，否则回退到推荐文件名', () => {
    expect(resolveEffectivePushName('  自定义名称  ', '默认名称')).toBe('自定义名称')
    expect(resolveEffectivePushName('   ', '默认名称')).toBe('默认名称')
    expect(resolveEffectivePushName('', '')).toBe('')
  })

  it('文件重复占用时必须阻止提交', () => {
    const duplicatedNativeFile = createNativeFile('重复文件.pdf')
    const groups: LightingGroup[] = [
      createGroup({
        id: 'g1',
        sphereFile: { id: 'f1', file: duplicatedNativeFile, preview: null },
      }),
      createGroup({
        id: 'g2',
        distributionFile: { id: 'f2', file: duplicatedNativeFile, preview: null },
      }),
    ]
    const fixedTemplates = resolveFixedLightingTemplates([
      createTemplate({ id: 'sphere-tpl', code: 'integrating_sphere' }),
      createTemplate({ id: 'distribution-tpl', code: 'light_distribution' }),
    ])

    const result = validateLightingGroups(groups, fixedTemplates)

    expect(result.canSubmit).toBe(false)
    expect(result.globalErrors).toContain('存在重复占用文件的分组，请先调整后再提交')
  })

  it('只返回可提交分组涉及的文件，不依赖公共文件池', () => {
    const sphereFile = createFile('sphere-1', '积分球样本.pdf')
    const distributionFile = createFile('distribution-1', '光分布样本.pdf')
    const invalidDistributionFile = createFile('distribution-2', '缺模板文件.pdf')
    const groups: LightingGroup[] = [
      createGroup({ id: 'g1', sphereFile, distributionFile }),
      createGroup({ id: 'g2', distributionFile: invalidDistributionFile }),
      createGroup({ id: 'g3' }),
    ]
    const fixedTemplates = resolveFixedLightingTemplates([
      createTemplate({ id: 'sphere-tpl', code: 'integrating_sphere' }),
    ])

    const submittableGroups = getSubmittableLightingGroups(groups, fixedTemplates)
    const submittableFiles = getSubmittableUploadFiles(groups, fixedTemplates)

    expect(submittableGroups.map(group => group.id)).toEqual([])
    expect(submittableFiles.map(file => file.id)).toEqual([])

    const fixedTemplates2 = resolveFixedLightingTemplates([
      createTemplate({ id: 'sphere-tpl', code: 'integrating_sphere' }),
      createTemplate({ id: 'distribution-tpl', code: 'light_distribution' }),
    ])
    const submittableGroups2 = getSubmittableLightingGroups(groups, fixedTemplates2)
    const submittableFiles2 = getSubmittableUploadFiles(groups, fixedTemplates2)

    expect(submittableGroups2.map(group => group.id)).toEqual(['g1', 'g2'])
    expect(submittableFiles2.map(file => file.id)).toEqual(['sphere-1', 'distribution-1', 'distribution-2'])
  })

  it('选中文件时能识别该文件是否已被其他分组占用', () => {
    const existingFile = createNativeFile('同一文件.pdf', 1720000000000)
    const groups: LightingGroup[] = [
      createGroup({
        id: 'g1',
        sphereFile: { id: 'f1', file: existingFile, preview: null },
      }),
      createGroup({ id: 'g2' }),
    ]

    expect(isLightingFileUsedInOtherGroups(groups, 'g2', 'distributionFile', createNativeFile('同一文件.pdf', 1720000000000))).toBe(true)
    expect(isLightingFileUsedInOtherGroups(groups, 'g1', 'distributionFile', createNativeFile('同一文件.pdf', 1720000000000))).toBe(false)
    expect(isLightingFileUsedInOtherGroups(groups, 'g2', 'distributionFile', createNativeFile('另一个文件.pdf', 1720000000001))).toBe(false)
  })
})
