import { Outlet, Navigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { PageLoader } from '@/components/ui/spinner'
import Logo from '@/assets/neoflow-logo.png'

export function AuthLayout() {
  const { session, isLoading } = useAuth()

  if (isLoading) {
    return <PageLoader />
  }

  if (session) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="min-h-screen flex">
      {/* Left Panel - Branding */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-center items-center p-12 relative overflow-hidden">
        {/* Background Effect */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary-900/50 via-bg-primary to-accent-900/30" />
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary-500/20 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-72 h-72 bg-accent-500/20 rounded-full blur-3xl" />

        <div className="relative z-10 text-center">
          <div className="flex items-center justify-center mb-8">
            <img src={Logo} alt="NeoFlow Logo" className="h-20 w-20 rounded-2xl shadow-2xl shadow-primary-500/30 animate-pulse-glow" />
          </div>
          <h1 className="text-4xl font-bold gradient-text mb-4">NeoFlow 智能文档处理平台</h1>
          <p className="text-lg text-text-secondary max-w-md">
            基于 LangGraph 的智能文档识别平台
          </p>

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
                className={`p-4 rounded-xl bg-bg-card/50 border border-border-default animate-slideInUp stagger-${i + 1}`}
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
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8 lg:p-12">
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

