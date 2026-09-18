import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unitIndex = 0

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }

  return `${value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`
}

export function formatDate(value?: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function getStatusText(status?: string | null): string {
  switch (status) {
    case 'pending':
      return '待处理'
    case 'uploaded':
      return '已上传'
    case 'queued':
      return '排队中'
    case 'processing':
      return '处理中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '处理失败'
    default:
      return status || '-'
  }
}

export function getStatusColor(status?: string | null): string {
  switch (status) {
    case 'completed':
      return 'bg-success-500/10 text-success-500 border border-success-500/20'
    case 'queued':
    case 'processing':
    case 'pending':
    case 'uploaded':
      return 'bg-accent-400/10 text-accent-400 border border-accent-400/20'
    case 'failed':
      return 'bg-error-500/10 text-error-500 border border-error-500/20'
    default:
      return 'bg-bg-hover text-text-secondary border border-border-default'
  }
}
