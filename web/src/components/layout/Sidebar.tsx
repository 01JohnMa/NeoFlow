import { Link, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { cn } from '@/lib/utils'
import { useUIStore, useAuthStore, useProfileStore } from '@/store/useStore'
import {
  LayoutDashboard,
  Upload,
  FileText,
  FileSearch,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Settings,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import Logo from '@/assets/neoflow-logo.png'

const navigation = [
  { name: '仪表盘', href: '/', icon: LayoutDashboard },
  { name: '上传文档', href: '/upload', icon: Upload },
  { name: '文档列表', href: '/documents', icon: FileText },
  { name: '解析结果', href: '/parse', icon: FileSearch },
]

export function Sidebar() {
  const location = useLocation()
  const { sidebarOpen, toggleSidebar, setSidebarOpen } = useUIStore()
  const { user } = useAuthStore()
  const { profile } = useProfileStore()
  const { signOut } = useAuth()
  const isAdmin = profile?.role === 'tenant_admin' || profile?.role === 'super_admin'

  // 移动端点击导航后关闭侧边栏
  const handleNavClick = () => {
    if (window.innerWidth < 768) {
      setSidebarOpen(false)
    }
  }

  useEffect(() => {
    if (!sidebarOpen) return
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSidebarOpen(false)
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [setSidebarOpen, sidebarOpen])

  return (
    <>
      {/* 移动端遮罩层 */}
      {sidebarOpen && (
        <button
          type="button"
          aria-label="关闭导航"
          className="fixed inset-0 z-30 cursor-pointer bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      
      <aside
        className={cn(
          'fixed left-0 top-0 z-40 h-screen transition-all duration-300 ease-in-out',
          'border-r border-border-default/70 bg-bg-secondary/95 backdrop-blur-xl',
          // 移动端：抽屉式，通过 translate 控制显隐
          sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
          // PC端：保持原有宽度逻辑
          sidebarOpen ? 'w-64' : 'md:w-20 w-64'
        )}
      >
      {/* Logo */}
      <div className="flex h-16 items-center justify-between px-4 border-b border-border-default/70">
        <Link to="/" className="flex items-center gap-3">
          <img src={Logo} alt="NeoFlow Logo" className="h-10 w-10 rounded-xl shadow-lg shadow-primary-500/25" />
          {sidebarOpen && (
            <span className="font-semibold text-text-primary gradient-text">
              NeoFlow
            </span>
          )}
        </Link>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={sidebarOpen ? '收起导航' : '展开导航'}
          title={sidebarOpen ? '收起导航' : '展开导航'}
          aria-expanded={sidebarOpen}
          onClick={toggleSidebar}
          className="text-text-muted hover:text-text-primary"
        >
          {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </Button>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 p-3">
        {sidebarOpen && <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-text-muted">Workspace</p>}
        {navigation.map((item) => {
          const isActive = location.pathname === item.href
          return (
            <Link
              key={item.name}
              to={item.href}
              onClick={handleNavClick}
              aria-current={isActive ? 'page' : undefined}
              title={!sidebarOpen ? item.name : undefined}
              className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-primary-500/15 text-primary-300 border border-primary-500/30 shadow-sm shadow-primary-500/10'
                  : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
              )}
            >
              <item.icon className={cn('h-5 w-5 flex-shrink-0', isActive && 'text-primary-400')} />
              {sidebarOpen && <span>{item.name}</span>}
            </Link>
          )
        })}

        {/* 管理员入口 */}
        {isAdmin && (() => {
          const isActive = location.pathname === '/admin'
          return (
            <Link
              to="/admin"
              onClick={handleNavClick}
              aria-current={isActive ? 'page' : undefined}
              title={!sidebarOpen ? '系统配置' : undefined}
              className={cn(
                'mt-1 flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-primary-500/15 text-primary-300 border border-primary-500/30'
                  : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
              )}
            >
              <Settings className={cn('h-5 w-5 flex-shrink-0', isActive && 'text-primary-400')} />
              {sidebarOpen && <span>系统配置</span>}
            </Link>
          )
        })()}
      </nav>

      {/* User Info & Logout */}
      <div className="absolute bottom-0 left-0 right-0 border-t border-border-default p-3">
        {sidebarOpen && user && (
          <div className="mb-3 px-3 py-2 rounded-lg bg-bg-card">
            <p className="text-xs text-text-muted">当前用户</p>
            <p className="text-sm text-text-primary truncate">{user.email}</p>
          </div>
        )}
        <Button
          variant="ghost"
          aria-label="退出登录"
          title="退出登录"
          className={cn(
            'w-full justify-start gap-3 text-text-secondary hover:text-error-500',
            !sidebarOpen && 'justify-center px-0'
          )}
          onClick={signOut}
        >
          <LogOut className="h-5 w-5" />
          {sidebarOpen && <span>退出登录</span>}
        </Button>
      </div>
    </aside>
    </>
  )
}
