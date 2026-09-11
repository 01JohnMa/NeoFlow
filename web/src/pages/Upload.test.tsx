import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Upload } from '@/pages/Upload'

const profileState = vi.hoisted(() => ({
  tenantName: '测试部门' as string | null,
  tenantCode: 'quality' as string | null,
  templates: [] as Array<{ id: string; name: string; code: string; required_doc_count: number; is_active?: boolean }>,
  isLoading: false,
}))

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => profileState,
}))

vi.mock('@/hooks/useDocuments', () => ({
  useUploadDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useProcessDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}))

describe('Upload page', () => {
  it('只提供单文档上传入口', () => {
    profileState.tenantName = '测试部门'
    profileState.tenantCode = 'quality'
    profileState.templates = [
      { id: 'tpl-inspection', name: '检测报告', code: 'inspection_report', required_doc_count: 1 },
      { id: 'tpl-express', name: '快递单', code: 'express', required_doc_count: 1 },
    ]

    const html = renderToStaticMarkup(<Upload />)

    expect(html).toContain('选择文档类型')
    expect(html).toContain('检测报告')
    expect(html).toContain('快递单')
    expect(html).not.toContain('批量')
    expect(html).not.toContain('配对')
  })

  it('未选择部门时提示先选择部门', () => {
    profileState.tenantName = null
    profileState.tenantCode = null
    profileState.templates = []

    const html = renderToStaticMarkup(<Upload />)

    expect(html).toContain('请先选择所属部门')
  })
})
