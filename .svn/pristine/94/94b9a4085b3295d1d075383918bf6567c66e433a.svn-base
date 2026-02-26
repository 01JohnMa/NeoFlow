import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { supabase } from '@/lib/supabase'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor - add auth token
api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token) {
      config.headers.Authorization = `Bearer ${session.access_token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Check if error is auth-related
const isAuthError = (error: AxiosError): boolean => {
  const status = error.response?.status
  if (status === 401) return true
  
  // Check if 500 error contains auth-related message
  if (status === 500) {
    const data = error.response?.data as Record<string, unknown> | undefined
    const detail = String(data?.detail || '').toLowerCase()
    return detail.includes('登录') || detail.includes('token') || detail.includes('过期')
  }
  return false
}

// Response interceptor - handle errors
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (isAuthError(error)) {
      // Token expired, try to refresh
      const { error: refreshError } = await supabase.auth.refreshSession()
      if (refreshError) {
        // Refresh failed, sign out
        await supabase.auth.signOut()
        window.location.href = '/login'
      } else if (error.config) {
        // Retry the request with fresh token
        return api.request(error.config)
      }
    }
    return Promise.reject(error)
  }
)

export default api



