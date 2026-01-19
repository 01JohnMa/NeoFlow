import { useEffect, useCallback } from 'react'
import { useProfileStore, UserProfile, Template } from '@/store/useStore'
import { useAuthStore } from '@/store/useStore'
import { api } from '@/services/api'

export function useProfile() {
  const { profile, templates, isLoading, setProfile, setTemplates, setLoading, reset } = useProfileStore()
  const { session } = useAuthStore()

  // 获取用户 profile
  const fetchProfile = useCallback(async () => {
    if (!session) {
      reset()
      return
    }

    setLoading(true)
    try {
      const { data } = await api.get<UserProfile>('/tenants/me/profile')
      setProfile(data)
    } catch (error) {
      console.error('获取用户信息失败:', error)
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }, [session, setProfile, setLoading, reset])

  // 获取用户可用的模板
  const fetchTemplates = useCallback(async () => {
    if (!session) {
      setTemplates([])
      return
    }

    try {
      const { data } = await api.get<Template[]>('/tenants/me/templates')
      setTemplates(data || [])
    } catch (error) {
      console.error('获取模板列表失败:', error)
      setTemplates([])
    }
  }, [session, setTemplates])

  // 初始化
  useEffect(() => {
    if (session) {
      fetchProfile()
      fetchTemplates()
    } else {
      reset()
    }
  }, [session, fetchProfile, fetchTemplates, reset])

  // 更新 profile
  const updateProfile = useCallback(async (data: { tenant_id?: string; display_name?: string }) => {
    try {
      const { data: result } = await api.put('/tenants/me/profile', data)
      if (result?.profile) {
        // 重新获取完整的 profile
        await fetchProfile()
        await fetchTemplates()
      }
      return result
    } catch (error) {
      console.error('更新用户信息失败:', error)
      throw error
    }
  }, [fetchProfile, fetchTemplates])

  return {
    profile,
    templates,
    isLoading,
    fetchProfile,
    fetchTemplates,
    updateProfile,
    // 便捷方法
    isSuperAdmin: profile?.role === 'super_admin',
    isTenantAdmin: profile?.role === 'tenant_admin' || profile?.role === 'super_admin',
    tenantName: profile?.tenant_name,
    tenantCode: profile?.tenant_code,
    displayName: profile?.display_name,
  }
}

export default useProfile
