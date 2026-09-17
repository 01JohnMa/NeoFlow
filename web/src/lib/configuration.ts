import type { ConfigurationStatus, ConfigurationType } from '@/types'

export const CONFIGURATION_STATUS_LABELS: Record<ConfigurationStatus, string> = {
  draft: '草稿',
  published: '已发布',
  archived: '已归档',
}

export const CONFIGURATION_TYPE_LABELS: Record<ConfigurationType, string> = {
  parse: '解析',
  extract: '提取',
  classify: '分类',
  split: '拆分',
  composite: '组合提取',
}

export const IMPLEMENTED_CONFIGURATION_TYPES: ConfigurationType[] = ['parse', 'extract', 'classify', 'split']

export function configurationStatusVariant(
  status: ConfigurationStatus,
): 'success' | 'warning' | 'secondary' {
  if (status === 'published') return 'success'
  if (status === 'draft') return 'warning'
  return 'secondary'
}
