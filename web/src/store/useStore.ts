import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, Session } from '@supabase/supabase-js'

// 用户 Profile 类型
export interface UserProfile {
  user_id: string
  tenant_id: string | null
  tenant_name: string | null
  tenant_code: string | null
  role: 'super_admin' | 'tenant_admin' | 'user'
  display_name: string | null
}

// 模板类型
export interface Template {
  id: string
  name: string
  code: string
  description?: string
  process_mode: 'single' | 'merge'
  required_doc_count: number
}

// 合并规则类型
export interface MergeRule {
  id: string
  template_id: string
  doc_type_a: string
  doc_type_b: string
  sub_template_a_id: string
  sub_template_b_id: string
}

interface AuthState {
  user: User | null
  session: Session | null
  isLoading: boolean
  setUser: (user: User | null) => void
  setSession: (session: Session | null) => void
  setLoading: (loading: boolean) => void
  reset: () => void
}

// Profile Store
interface ProfileState {
  profile: UserProfile | null
  templates: Template[]
  mergeRules: MergeRule[]
  isLoading: boolean
  setProfile: (profile: UserProfile | null) => void
  setTemplates: (templates: Template[]) => void
  setMergeRules: (rules: MergeRule[]) => void
  setLoading: (loading: boolean) => void
  reset: () => void
}

interface UIState {
  sidebarOpen: boolean
  theme: 'dark' | 'light'
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setTheme: (theme: 'dark' | 'light') => void
}

interface UploadState {
  uploadProgress: Record<string, number>
  processingDocuments: Set<string>
  setUploadProgress: (id: string, progress: number) => void
  removeUploadProgress: (id: string) => void
  addProcessingDocument: (id: string) => void
  removeProcessingDocument: (id: string) => void
  isProcessing: (id: string) => boolean
}

// Auth Store
export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  session: null,
  isLoading: true,
  setUser: (user) => set({ user }),
  setSession: (session) => set({ session }),
  setLoading: (isLoading) => set({ isLoading }),
  reset: () => set({ user: null, session: null, isLoading: false }),
}))

// Profile Store
export const useProfileStore = create<ProfileState>()((set) => ({
  profile: null,
  templates: [],
  mergeRules: [],
  isLoading: false,
  setProfile: (profile) => set({ profile }),
  setTemplates: (templates) => set({ templates }),
  setMergeRules: (mergeRules) => set({ mergeRules }),
  setLoading: (isLoading) => set({ isLoading }),
  reset: () => set({ profile: null, templates: [], mergeRules: [], isLoading: false }),
}))

// 检测是否为移动端
const isMobile = () => typeof window !== 'undefined' && window.innerWidth < 768

// UI Store with persistence
export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarOpen: !isMobile(),
      theme: 'dark',
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: 'ui-storage',
      // 在 rehydrate 时检测移动端，覆盖持久化的值
      onRehydrateStorage: () => (state) => {
        if (state && isMobile()) {
          state.setSidebarOpen(false)
        }
      },
    }
  )
)

// Upload Store
export const useUploadStore = create<UploadState>()((set, get) => ({
  uploadProgress: {},
  processingDocuments: new Set(),
  setUploadProgress: (id, progress) =>
    set((state) => ({
      uploadProgress: { ...state.uploadProgress, [id]: progress },
    })),
  removeUploadProgress: (id) =>
    set((state) => {
      const { [id]: _, ...rest } = state.uploadProgress
      return { uploadProgress: rest }
    }),
  addProcessingDocument: (id) =>
    set((state) => {
      const newSet = new Set(state.processingDocuments)
      newSet.add(id)
      return { processingDocuments: newSet }
    }),
  removeProcessingDocument: (id) =>
    set((state) => {
      const newSet = new Set(state.processingDocuments)
      newSet.delete(id)
      return { processingDocuments: newSet }
    }),
  isProcessing: (id) => get().processingDocuments.has(id),
}))


