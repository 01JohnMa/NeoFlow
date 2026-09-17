import { useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useUIStore } from '@/store/useStore'

const pageTitles: Record<string, string> = {
  '/': '仪表盘',
  '/upload': '上传文档',
  '/documents': '文档列表',
  '/admin': '系统配置',
}

export function Header() {
  const location = useLocation()
  const title = pageTitles[location.pathname] || '文档详情'
  const { toggleSidebar } = useUIStore()

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border-default/70 bg-bg-primary/90 backdrop-blur-xl px-4 md:px-6">
      <div className="flex items-center gap-3">
        {/* 移动端汉堡菜单按钮 */}
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden text-text-secondary"
          aria-label="打开导航"
          onClick={toggleSidebar}
        >
          <Menu className="h-5 w-5" />
        </Button>
        <h1 className="text-lg font-semibold tracking-tight text-text-primary">{title}</h1>
      </div>

      <span className="hidden text-xs font-medium uppercase tracking-[0.18em] text-text-muted md:block">
        NeoFlow workspace
      </span>
    </header>
  )
}
