export function getAuthErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    const message = error.message.toLowerCase()

    if (message.includes('invalid login credentials')) return '邮箱或密码错误'
    if (message.includes('email not confirmed')) return '邮箱尚未验证，请先完成邮箱验证'
    if (message.includes('user already registered')) return '该邮箱已注册'
    if (message.includes('password')) return '密码不符合要求'

    return error.message || fallback
  }

  if (typeof error === 'string' && error.trim()) {
    return error
  }

  return fallback
}
