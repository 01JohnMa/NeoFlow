import { useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/useStore'
import { authService } from '@/services/auth'
import { supabase } from '@/lib/supabase'

export function useAuth() {
  const { user, session, isLoading, setUser, setSession, setLoading, reset } = useAuthStore()
  const navigate = useNavigate()

  // Initialize auth state
  useEffect(() => {
    let mounted = true

    const initAuth = async () => {
      try {
        const { session } = await authService.getSession()
        if (mounted) {
          setSession(session)
          setUser(session?.user ?? null)
        }
      } catch (error) {
        console.error('Auth init error:', error)
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    initAuth()

    // Listen to auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (mounted) {
        setSession(session)
        setUser(session?.user ?? null)
        setLoading(false)
      }
    })

    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [setUser, setSession, setLoading])

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



