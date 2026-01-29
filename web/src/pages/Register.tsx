import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { authService, Tenant } from '@/services/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Mail, Lock, AlertCircle, CheckCircle, Building2, User } from 'lucide-react'

export function Register() {
  const { signUp, isLoading } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [tenantId, setTenantId] = useState('')
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [loadingTenants, setLoadingTenants] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  // 加载租户列表
  useEffect(() => {
    const loadTenants = async () => {
      try {
        const list = await authService.getTenants()
        setTenants(list)
      } catch (err) {
        console.error('加载部门列表失败:', err)
      } finally {
        setLoadingTenants(false)
      }
    }
    loadTenants()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!email || !password) {
      setError('请填写所有必填字段')
      return
    }

    if (password.length < 6) {
      setError('密码长度至少为6位')
      return
    }

    if (password !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }

    if (!tenantId) {
      setError('请选择所属部门')
      return
    }

    try {
      const result = await signUp(email, password, tenantId, displayName || undefined)
      if (!result.session) {
        // Email confirmation required
        setSuccess(true)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '注册失败，请重试'
      setError(message)
    }
  }

  if (success) {
    return (
      <Card className="w-full animate-fadeIn">
        <CardContent className="pt-6">
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-success-500/10 flex items-center justify-center">
              <CheckCircle className="h-8 w-8 text-success-500" />
            </div>
            <h2 className="text-xl font-semibold text-text-primary">注册成功！</h2>
            <p className="text-text-secondary">
              请检查您的邮箱并点击验证链接完成注册。
            </p>
            <Link to="/login">
              <Button variant="outline">返回登录</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="w-full animate-fadeIn">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl font-bold text-center">创建账户</CardTitle>
        <CardDescription className="text-center">
          注册新账户开始使用 NeoFlow
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-error-500/10 border border-error-500/20 text-error-500 text-sm">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="email" required>邮箱</Label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <Input
                id="email"
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="pl-10"
                autoComplete="email"
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="displayName">显示名称</Label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <Input
                id="displayName"
                type="text"
                placeholder="您的姓名（可选）"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="pl-10"
                autoComplete="name"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="tenant" required>所属部门</Label>
            <div className="relative">
              <Building2 className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted z-10 pointer-events-none" />
              <Select 
                id="tenant"
                value={tenantId} 
                onChange={(e) => setTenantId(e.target.value)}
                disabled={loadingTenants}
                className="pl-10"
                required
              >
                <option value="" disabled>
                  {loadingTenants ? "加载中..." : "请选择部门"}
                </option>
                {tenants.map((tenant) => (
                  <option key={tenant.id} value={tenant.id}>
                    {tenant.name}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="password" required>密码</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <Input
                id="password"
                type="password"
                placeholder="至少6位字符"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="pl-10"
                autoComplete="new-password"
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword" required>确认密码</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <Input
                id="confirmPassword"
                type="password"
                placeholder="再次输入密码"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="pl-10"
                autoComplete="new-password"
                required
              />
            </div>
          </div>

          <Button type="submit" className="w-full" loading={isLoading}>
            注册
          </Button>
        </form>
      </CardContent>
      <CardFooter className="flex flex-col gap-4">
        <div className="text-center text-sm text-text-secondary">
          已有账户？{' '}
          <Link to="/login" className="text-primary-400 hover:text-primary-300 font-medium transition-colors">
            立即登录
          </Link>
        </div>
      </CardFooter>
    </Card>
  )
}



