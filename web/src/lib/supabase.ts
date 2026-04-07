import { createClient } from '@supabase/supabase-js'
import { resolveSupabaseUrl } from './supabaseUrl'

const rawSupabaseUrl = import.meta.env.VITE_SUPABASE_URL || '/supabase'
const supabaseUrl = resolveSupabaseUrl(rawSupabaseUrl, window.location.origin)
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || ''

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})
