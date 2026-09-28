import { supabase } from '@/lib/supabase'
import { api } from './api'
import type { AuthChangeEvent, User, Session } from '@supabase/supabase-js'

export interface AuthResponse {
  user: User | null
  session: Session | null
  error: Error | null
}

export interface SignUpOptions {
  email: string
  password: string
  displayName?: string
}

// localStorage keys for pending profile data (used when email confirmation is required)
const PENDING_DISPLAY_NAME_KEY = 'neoflow_pending_display_name'

// Cache pending profile data for first login
export function cachePendingProfile(displayName?: string) {
  if (displayName) {
    localStorage.setItem(PENDING_DISPLAY_NAME_KEY, displayName)
  }
}

// Get cached pending profile data
export function getPendingProfile(): { displayName?: string } {
  return {
    displayName: localStorage.getItem(PENDING_DISPLAY_NAME_KEY) || undefined,
  }
}

// Clear cached pending profile data
export function clearPendingProfile() {
  // Remove the legacy key once; tenant scope is no longer browser-managed.
  localStorage.removeItem('neoflow_pending_tenant_id')
  localStorage.removeItem(PENDING_DISPLAY_NAME_KEY)
}

export const authService = {
  // Sign up with email/password. Tenant scope is assigned by the integrating platform.
  async signUp(options: SignUpOptions): Promise<AuthResponse> {
    const { email, password, displayName } = options

    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          display_name: displayName || email,
        }
      }
    })

    // Display name may be persisted after authentication. Tenant scope is
    // never accepted from the browser and is assigned by the platform.
    if (!error && data.user && displayName) {
      if (data.session) {
        try {
          await api.put('/tenants/me/profile', { display_name: displayName })
        } catch {
          cachePendingProfile(displayName)
        }
      } else {
        cachePendingProfile(displayName)
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
    console.log('Supabase signIn result:', { data, error })
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
  onAuthStateChange(callback: (event: AuthChangeEvent, session: Session | null) => void) {
    return supabase.auth.onAuthStateChange((event: AuthChangeEvent, session: Session | null) => {
      callback(event, session)
    })
  },
}

export default authService

