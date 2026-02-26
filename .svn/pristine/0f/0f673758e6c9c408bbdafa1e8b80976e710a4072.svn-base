import { useLocation } from 'react-router-dom'
import { Bell, Search, Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useUIStore } from '@/store/useStore'

const pageTitles: Record<string, string> = {
  '/': '仪表盘',
  '/upload': '上传文档',
  '/documents': '文档列表',
}

export function Header() {
  const location = useLocation()
  const title = pageTitles[location.pathname] || '文档详情'
  const { toggleSidebar } = useUIStore()

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border-default bg-bg-primary/80 backdrop-blur-xl px-4 md:px-6">
      <div className="flex items-center gap-3">
        {/* 移动端汉堡菜单按钮 */}
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden text-text-secondary"
          onClick={toggleSidebar}
        >
          <Menu className="h-5 w-5" />
        </Button>
        <h1 className="text-xl font-semibold text-text-primary">{title}</h1>
      </div>

      <div className="flex items-center gap-4">
        {/* Search */}
        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <Input
            placeholder="搜索文档..."
            className="w-64 pl-9 bg-bg-secondary border-border-default"
          />
        </div>

        {/* Notifications */}
        <Button variant="ghost" size="icon" className="text-text-secondary">
          <Bell className="h-5 w-5" />
        </Button>
      </div>
    </header>
  )
}


