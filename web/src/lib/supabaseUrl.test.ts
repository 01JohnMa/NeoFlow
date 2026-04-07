import { describe, expect, it } from 'vitest'
import { resolveSupabaseUrl } from './supabaseUrl'

describe('resolveSupabaseUrl', () => {
  it('将相对 Supabase 路径解析为当前站点的绝对地址', () => {
    expect(resolveSupabaseUrl('/supabase', 'http://localhost:8080')).toBe('http://localhost:8080/supabase')
  })

  it('保留绝对 Supabase 地址不变', () => {
    expect(resolveSupabaseUrl('https://example.com/supabase', 'http://localhost:8080')).toBe('https://example.com/supabase')
  })
})
