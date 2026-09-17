import { Outlet, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/store/useStore'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { useRequireAuth } from '@/hooks/useAuth'
import { PageLoader } from '@/components/ui/spinner'

export function MainLayout() {
  const { sidebarOpen } = useUIStore()
  const { isLoading, isAuthenticated } = useRequireAuth()
  const location = useLocation()

  // Playground（Parse 页）自带顶栏与浅色作用域，不使用全局 Header 与页面留白
  const isPlayground =
    location.pathname === '/parse' || location.pathname.startsWith('/parse?')

  if (isLoading) {
    return <PageLoader />
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="min-h-screen bg-bg-primary">
      <Sidebar />
      <div
        className={cn(
          'transition-all duration-300 ease-in-out',
          sidebarOpen ? 'md:ml-64 ml-0' : 'md:ml-20 ml-0'
        )}
      >
        {!isPlayground && <Header />}
        {isPlayground ? (
          <main className="h-screen overflow-hidden bg-bg-primary">
            <Outlet />
          </main>
        ) : (
          <main className="p-4 md:p-6 max-w-[1600px]">
            <Outlet />
          </main>
        )}
      </div>
    </div>
  )
}
