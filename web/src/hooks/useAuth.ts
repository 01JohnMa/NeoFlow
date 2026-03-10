import { useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/useStore'
import { authService } from '@/services/auth'
import { supabase } from '@/lib/supabase'
import type { Session } from '@supabase/supabase-js'

let authInitialized = false
let authInitPromise: Promise<void> | null = null
let authSubscription: { unsubscribe: () => void } | null = null
let authConsumerCount = 0

function applySessionToStore(session: Session | null) {
  const { setSession, setUser, setLoading } = useAuthStore.getState()
  setSession(session)
  setUser(session?.user ?? null)
  setLoading(false)
}

async function ensureAuthInitialized() {
  if (authInitialized) return
  if (authInitPromise) {
    await authInitPromise
    return
  }

  authInitPromise = (async () => {
    try {
      const { session } = await authService.getSession()
      applySessionToStore(session)
    } catch (error) {
      console.error('Auth init error:', error)
      const { setLoading } = useAuthStore.getState()
      setLoading(false)
    }

    if (!authSubscription) {
      const { data } = supabase.auth.onAuthStateChange((_event, session) => {
        applySessionToStore(session)
      })
      authSubscription = data.subscription
    }

    authInitialized = true
  })()

  await authInitPromise
}

export function useAuth() {
  const { user, session, isLoading, setUser, setSession, setLoading, reset } = useAuthStore()
  const navigate = useNavigate()

  // Initialize auth state
  useEffect(() => {
    authConsumerCount += 1
    ensureAuthInitialized()
    return () => {
      authConsumerCount -= 1
      if (authConsumerCount <= 0) {
        if (authSubscription) {
          authSubscription.unsubscribe()
          authSubscription = null
        }
        authInitialized = false
        authInitPromise = null
        authConsumerCount = 0
      }
    }
  }, [])

  // Sign in
  const signIn = useCallback(async (email: string, password: string) => {
    setLoading(true)
    const result = await authService.signIn(email, password)
    setLoading(false)

    if (result.error) {
      throw result.error
    }

    setUser(result.user)
    setSession(result.session)
    navigate('/')
    return result
  }, [navigate, setUser, setSession, setLoading])

  // Sign up with optional tenant
  const signUp = useCallback(async (
    email: string, 
    password: string,
    tenantId?: string,
    displayName?: string
  ) => {
    setLoading(true)
    const result = await authService.signUp({ 
      email, 
      password, 
      tenantId,
      displayName 
    })
    setLoading(false)

    if (result.error) {
      throw result.error
    }

    // If email confirmation is disabled, sign in directly
    if (result.session) {
      setUser(result.user)
      setSession(result.session)
      navigate('/')
    }

    return result
  }, [navigate, setUser, setSession, setLoading])

  // Sign out
  const signOut = useCallback(async () => {
    setLoading(true)
    await authService.signOut()
    reset()
    navigate('/login')
  }, [navigate, reset, setLoading])

  return {
    user,
    session,
    isLoading,
    isAuthenticated: !!session,
    signIn,
    signUp,
    signOut,
  }
}

// Hook to require authentication
export function useRequireAuth() {
  const { isAuthenticated, isLoading } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/login', { replace: true })
    }
  }, [isAuthenticated, isLoading, navigate])

  return { isAuthenticated, isLoading }
}



