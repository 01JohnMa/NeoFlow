import { Outlet, Navigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import Logo from '@/assets/neoflow-logo.png'

export function AuthLayout() {
  const { session } = useAuth()

  // 已登录则跳转首页
  if (session) {
    return <Navigate to="/" replace />
  }

  // 仅在初始加载时显示 PageLoader，不影响登录/注册表单
  // 注意：不能因为 isLoading 卸载子组件，否则会丢失表单状态

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary lg:grid lg:grid-cols-[1.05fr_0.95fr]">
      {/* Left Panel - Branding */}
      <div className="relative hidden flex-col items-center justify-center overflow-hidden border-r border-border-default/70 p-12 lg:flex">
        {/* Background Effect */}
        <div className="absolute inset-0 bg-bg-secondary" />
        <div className="absolute inset-0 opacity-60 [background-image:radial-gradient(rgba(124,92,255,.12)_1px,transparent_1px)] [background-size:24px_24px]" />
        <div className="absolute -left-20 top-1/4 h-96 w-96 rounded-full bg-primary-500/15 blur-3xl" />

        <div className="relative z-10 text-center">
          <div className="flex items-center justify-center mb-8">
            <img src={Logo} alt="NeoFlow Logo" className="h-20 w-20 rounded-2xl shadow-2xl shadow-primary-500/30 animate-pulse-glow" />
          </div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-primary-300">Document intelligence workspace</p>
          <h1 className="mb-4 text-4xl font-semibold tracking-tight text-text-primary">NeoFlow 智能文档处理平台</h1>

          {/* Features */}
          <div className="mt-12 grid grid-cols-2 gap-6 text-left">
            {[
              { title: '智能识别', desc: 'AI 驱动的 OCR 技术' },
              { title: '多类型支持', desc: '检验/快递/抽样单' },
              { title: '人工审核', desc: '结果可编辑修改' },
              { title: '移动端适配', desc: '支持拍照上传' },
            ].map((feature, i) => (
              <div
                key={feature.title}
                className={`rounded-xl border border-border-default bg-bg-card/80 p-4 animate-slideInUp stagger-${i + 1}`}
                style={{ animationFillMode: 'both' }}
              >
                <h3 className="font-medium text-text-primary">{feature.title}</h3>
                <p className="text-sm text-text-muted">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right Panel - Auth Form */}
      <div className="flex w-full items-center justify-center p-6 sm:p-8 lg:p-12">
        <div className="w-full max-w-md">
          {/* Mobile Logo */}
          <div className="lg:hidden flex items-center justify-center mb-8">
            <img src={Logo} alt="NeoFlow Logo" className="h-16 w-16 rounded-xl shadow-lg" />
          </div>
          <Outlet />
        </div>
      </div>
    </div>
  )
}
