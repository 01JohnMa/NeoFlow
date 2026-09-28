import { useEffect, useCallback, useRef } from 'react'
import { useProfileStore, UserProfile } from '@/store/useStore'
import { useAuthStore } from '@/store/useStore'
import { api } from '@/services/api'
import { getPendingProfile, clearPendingProfile } from '@/services/auth'

export function useProfile() {
  const { profile, isLoading, setProfile, setLoading, reset } = useProfileStore()
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

      if (data && !pendingSyncAttempted.current) {
        const pending = getPendingProfile()
        if (pending.displayName && pending.displayName !== data.display_name) {
          pendingSyncAttempted.current = true
          try {
            await api.put('/tenants/me/profile', {
              display_name: pending.displayName,
            })
            clearPendingProfile()
            const { data: updatedData } = await api.get<UserProfile>('/tenants/me/profile')
            setProfile(updatedData)
          } catch (updateError) {
            console.error('补充显示名称失败:', updateError)
            setProfile(data)
          }
        } else {
          setProfile(data)
        }
      } else {
        setProfile(data)
        if (data?.display_name) {
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

  useEffect(() => {
    if (userId) {
      fetchProfile()
    } else {
      reset()
    }
  }, [userId, fetchProfile, reset])

  const updateProfile = useCallback(async (data: { display_name?: string }) => {
    try {
      const { data: result } = await api.put('/tenants/me/profile', data)
      if (result?.profile) {
        await fetchProfile()
      }
      return result
    } catch (error) {
      console.error('更新用户信息失败:', error)
      throw error
    }
  }, [fetchProfile])

  return {
    profile,
    isLoading,
    fetchProfile,
    updateProfile,
    isSuperAdmin: profile?.role === 'super_admin',
    isTenantAdmin: profile?.role === 'tenant_admin' || profile?.role === 'super_admin',
    tenantName: profile?.tenant_name,
    tenantCode: profile?.tenant_code,
    displayName: profile?.display_name,
  }
}

export default useProfile
