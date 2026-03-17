import { useEffect, useCallback, useRef } from 'react'
import { useProfileStore, UserProfile, Template, MergeRule } from '@/store/useStore'
import { useAuthStore } from '@/store/useStore'
import { api } from '@/services/api'
import { getPendingProfile, clearPendingProfile } from '@/services/auth'

export function useProfile() {
  const { profile, templates, mergeRules, isLoading, setProfile, setTemplates, setMergeRules, setLoading, reset } = useProfileStore()
  const { session } = useAuthStore()
  const userId = session?.user?.id
  // Track if we've already attempted to sync pending profile (avoid infinite loops)
  const pendingSyncAttempted = useRef(false)

  // 鑾峰彇鐢ㄦ埛 profile
  const fetchProfile = useCallback(async () => {
    if (!userId) {
      reset()
      pendingSyncAttempted.current = false
      return
    }

    setLoading(true)
    try {
      const { data } = await api.get<UserProfile>('/tenants/me/profile')
      
      // Check if profile is missing tenant_id and we have pending data from registration
      if (data && !data.tenant_id && !pendingSyncAttempted.current) {
        const pending = getPendingProfile()
        if (pending.tenantId) {
          console.log('妫€娴嬪埌缂撳瓨鐨?tenant_id锛屽皾璇曟洿鏂?profile...')
          pendingSyncAttempted.current = true
          try {
            await api.put('/tenants/me/profile', {
              tenant_id: pending.tenantId,
              display_name: pending.displayName || data.display_name
            })
            clearPendingProfile()
            // Re-fetch to get updated profile
            const { data: updatedData } = await api.get<UserProfile>('/tenants/me/profile')
            setProfile(updatedData)
            console.log('Profile 宸叉垚鍔熻ˉ鍏?tenant_id')
          } catch (updateError) {
            console.error('琛ュ厖 tenant_id 澶辫触:', updateError)
            setProfile(data)
          }
        } else {
          setProfile(data)
        }
      } else {
        setProfile(data)
        // Clear any stale pending data if profile already has tenant_id
        if (data?.tenant_id) {
          clearPendingProfile()
        }
      }
    } catch (error) {
      console.error('鑾峰彇鐢ㄦ埛淇℃伅澶辫触:', error)
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }, [userId, setProfile, setLoading, reset])

  // 鑾峰彇鐢ㄦ埛鍙敤鐨勬ā鏉?
  const fetchTemplates = useCallback(async () => {
    if (!userId) {
      setTemplates([])
      return
    }

    try {
      const { data } = await api.get<Template[]>('/tenants/me/templates')
      setTemplates(data || [])
    } catch (error) {
      console.error('鑾峰彇妯℃澘鍒楄〃澶辫触:', error)
      setTemplates([])
    }
  }, [userId, setTemplates])

  // 鑾峰彇鍚堝苟瑙勫垯锛堢敤浜?merge 妯″紡锛?
  const fetchMergeRules = useCallback(async () => {
    if (!userId) {
      setMergeRules([])
      return
    }

    try {
      const { data } = await api.get<MergeRule[]>('/tenants/me/merge-rules')
      setMergeRules(data || [])
    } catch (error) {
      console.error('鑾峰彇鍚堝苟瑙勫垯澶辫触:', error)
      setMergeRules([])
    }
  }, [userId, setMergeRules])

  // 鍒濆鍖?
  useEffect(() => {
    if (userId) {
      fetchProfile()
      fetchTemplates()
      fetchMergeRules()
    } else {
      reset()
    }
  }, [userId, fetchProfile, fetchTemplates, fetchMergeRules, reset])

  // 鏇存柊 profile
  const updateProfile = useCallback(async (data: { tenant_id?: string; display_name?: string }) => {
    try {
      const { data: result } = await api.put('/tenants/me/profile', data)
      if (result?.profile) {
        // 閲嶆柊鑾峰彇瀹屾暣鐨?profile
        await fetchProfile()
        await fetchTemplates()
      }
      return result
    } catch (error) {
      console.error('鏇存柊鐢ㄦ埛淇℃伅澶辫触:', error)
      throw error
    }
  }, [fetchProfile, fetchTemplates])

  return {
    profile,
    templates,
    mergeRules,
    isLoading,
    fetchProfile,
    fetchTemplates,
    fetchMergeRules,
    updateProfile,
    // 渚挎嵎鏂规硶
    isSuperAdmin: profile?.role === 'super_admin',
    isTenantAdmin: profile?.role === 'tenant_admin' || profile?.role === 'super_admin',
    tenantName: profile?.tenant_name,
    tenantCode: profile?.tenant_code,
    displayName: profile?.display_name,
  }
}

export default useProfile
