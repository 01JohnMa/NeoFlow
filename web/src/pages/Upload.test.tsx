import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Upload } from '@/pages/Upload'

const profileState = vi.hoisted(() => ({
  tenantCode: 'quality' as string | null,
  profile: {
    user_id: 'user-1',
    tenant_id: 'tenant-1',
    tenant_name: '测试部门',
    tenant_code: 'quality',
    role: 'user' as const,
    display_name: null,
  } as null | { user_id: string; tenant_id: string; tenant_name: string | null; tenant_code: string | null; role: 'user'; display_name: string | null },
  isLoading: false,
  fetchProfile: vi.fn(),
}))

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => profileState,
}))

vi.mock('@/hooks/useDocuments', () => ({
  useUploadDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}))

describe('Upload page', () => {
  it('只提供纯上传入口，不展示模板选择', () => {
    profileState.tenantCode = 'quality'
    profileState.profile = {
      user_id: 'user-1',
      tenant_id: 'tenant-1',
      tenant_name: '测试部门',
      tenant_code: 'quality',
      role: 'user',
      display_name: null,
    }

    const html = renderToStaticMarkup(<Upload />)

    expect(html).toContain('拖拽文件到此处或点击选择')
    expect(html).not.toContain('选择文档类型')
    expect(html).not.toContain('检测报告')
    expect(html).not.toContain('快递单')
    expect(html).not.toContain('上传并识别')
  })

  it('未选择部门时提示先选择部门', () => {
    profileState.tenantCode = null
    profileState.profile = null

    const html = renderToStaticMarkup(<Upload />)

    expect(html).toContain('请先选择所属部门')
  })
})
