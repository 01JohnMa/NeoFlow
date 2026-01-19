import { supabase } from '@/lib/supabase'
import { api } from './api'
import type { User, Session } from '@supabase/supabase-js'

export interface AuthResponse {
  user: User | null
  session: Session | null
  error: Error | null
}

export interface SignUpOptions {
  email: string
  password: string
  tenantId?: string
  displayName?: string
}

export interface Tenant {
  id: string
  name: string
  code: string
  description?: string
}

export const authService = {
  // Get available tenants for registration
  async getTenants(): Promise<Tenant[]> {
    try {
      const { data } = await api.get<Tenant[]>('/tenants')
      return data || []
    } catch (error) {
      console.error('获取租户列表失败:', error)
      return []
    }
  },

  // Sign up with email/password and optional tenant
  async signUp(options: SignUpOptions): Promise<AuthResponse> {
    const { email, password, tenantId, displayName } = options
    
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          display_name: displayName || email,
          tenant_id: tenantId,
        }
      }
    })
    
    // If signup successful and we have tenant_id, update profile
    if (!error && data.user && tenantId) {
      try {
        await api.put('/tenants/me/profile', {
          tenant_id: tenantId,
          display_name: displayName || email
        })
      } catch (profileError) {
        console.warn('更新用户 profile 失败:', profileError)
      }
    }
    
    return {
      user: data.user,
      session: data.session,
      error: error as Error | null,
    }
  },

  // Sign in with email/password
  async signIn(email: string, password: string): Promise<AuthResponse> {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    return {
      user: data.user,
      session: data.session,
      error: error as Error | null,
    }
  },

  // Sign out
  async signOut(): Promise<{ error: Error | null }> {
    const { error } = await supabase.auth.signOut()
    return { error: error as Error | null }
  },

  // Get current session
  async getSession(): Promise<{ session: Session | null; error: Error | null }> {
    const { data, error } = await supabase.auth.getSession()
    return {
      session: data.session,
      error: error as Error | null,
    }
  },

  // Get current user
  async getUser(): Promise<{ user: User | null; error: Error | null }> {
    const { data, error } = await supabase.auth.getUser()
    return {
      user: data.user,
      error: error as Error | null,
    }
  },

  // Refresh session
  async refreshSession(): Promise<AuthResponse> {
    const { data, error } = await supabase.auth.refreshSession()
    return {
      user: data.user,
      session: data.session,
      error: error as Error | null,
    }
  },

  // Reset password
  async resetPassword(email: string): Promise<{ error: Error | null }> {
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    return { error: error as Error | null }
  },

  // Update password
  async updatePassword(newPassword: string): Promise<{ error: Error | null }> {
    const { error } = await supabase.auth.updateUser({
      password: newPassword,
    })
    return { error: error as Error | null }
  },

  // Listen to auth changes
  onAuthStateChange(callback: (event: string, session: Session | null) => void) {
    return supabase.auth.onAuthStateChange((event, session) => {
      callback(event, session)
    })
  },
}

export default authService



