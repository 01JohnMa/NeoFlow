import { useEffect, useCallback, useRef } from 'react'
import { useProfileStore, UserProfile, Template } from '@/store/useStore'
import { useAuthStore } from '@/store/useStore'
import { api } from '@/services/api'
import { getPendingProfile, clearPendingProfile } from '@/services/auth'

export function useProfile() {
  const { profile, templates, isLoading, setProfile, setTemplates, setLoading, reset } = useProfileStore()
  const { session } = useAuthStore()
  const userId = session?.user?.id
  const pendingSyncAttempted = useRef(false)

  const fetchProfile = useCallback(async () => {
    if (!userId) {
      reset()
      pendingSyncAttempted.current = false
      return
    }

    setLoading(true)
    try {
      const { data } = await api.get<UserProfile>('/tenants/me/profile')

      if (data && !data.tenant_id && !pendingSyncAttempted.current) {
        const pending = getPendingProfile()
        if (pending.tenantId) {
          pendingSyncAttempted.current = true
          try {
            await api.put('/tenants/me/profile', {
              tenant_id: pending.tenantId,
              display_name: pending.displayName || data.display_name
            })
            clearPendingProfile()
            const { data: updatedData } = await api.get<UserProfile>('/tenants/me/profile')
            setProfile(updatedData)
          } catch (updateError) {
            console.error('补充 tenant_id 失败:', updateError)
            setProfile(data)
          }
        } else {
          setProfile(data)
        }
      } else {
        setProfile(data)
        if (data?.tenant_id) {
          clearPendingProfile()
        }
      }
    } catch (error) {
      console.error('获取用户信息失败:', error)
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }, [userId, setProfile, setLoading, reset])

  const fetchTemplates = useCallback(async () => {
    if (!userId) {
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
  }, [userId, setTemplates])

  useEffect(() => {
    if (userId) {
      fetchProfile()
      fetchTemplates()
    } else {
      reset()
    }
  }, [userId, fetchProfile, fetchTemplates, reset])

  const updateProfile = useCallback(async (data: { tenant_id?: string; display_name?: string }) => {
    try {
      const { data: result } = await api.put('/tenants/me/profile', data)
      if (result?.profile) {
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
    isSuperAdmin: profile?.role === 'super_admin',
    isTenantAdmin: profile?.role === 'tenant_admin' || profile?.role === 'super_admin',
    tenantName: profile?.tenant_name,
    tenantCode: profile?.tenant_code,
    displayName: profile?.display_name,
  }
}

export default useProfile
