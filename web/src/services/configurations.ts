import { api } from './api'
import type {
  Configuration,
  ConfigurationRevision,
  CreateConfigurationPayload,
  UpdateConfigurationPayload,
} from '@/types'

export interface ListConfigurationsParams {
  tenant_id?: string
  project_id?: string
  status?: string
  type?: string
}

export async function listConfigurations(
  params: ListConfigurationsParams = {},
): Promise<Configuration[]> {
  const { data } = await api.get<Configuration[]>('/admin/configurations', { params })
  return data || []
}

export async function createConfiguration(
  payload: CreateConfigurationPayload,
): Promise<Configuration> {
  const { data } = await api.post<{ success: boolean; data: Configuration }>(
    '/admin/configurations',
    payload,
  )
  return data.data
}

export async function getConfiguration(configurationId: string): Promise<Configuration> {
  const { data } = await api.get<Configuration>(`/admin/configurations/${configurationId}`)
  return data
}

export async function updateConfiguration(
  configurationId: string,
  payload: UpdateConfigurationPayload,
): Promise<Configuration> {
  const { data } = await api.put<{ success: boolean; data: Configuration }>(
    `/admin/configurations/${configurationId}`,
    payload,
  )
  return data.data
}

export async function publishConfiguration(configurationId: string): Promise<{
  configuration: Configuration
  revision: ConfigurationRevision
}> {
  const { data } = await api.post<{
    success: boolean
    data: { configuration: Configuration; revision: ConfigurationRevision }
  }>(`/admin/configurations/${configurationId}/publish`)
  return data.data
}

export async function archiveConfiguration(configurationId: string): Promise<Configuration> {
  const { data } = await api.post<{ success: boolean; data: Configuration }>(
    `/admin/configurations/${configurationId}/archive`,
  )
  return data.data
}

export async function appendFieldExample(
  configurationId: string,
  fieldKey: string,
  example: string,
): Promise<{ configuration: Configuration; revision: ConfigurationRevision | null }> {
  const { data } = await api.post<{
    success: boolean
    data: { configuration: Configuration; revision: ConfigurationRevision | null }
  }>(
    `/admin/configurations/${configurationId}/fields/${encodeURIComponent(fieldKey)}/examples`,
    { example },
  )
  return data.data
}

export async function listRevisions(configurationId: string): Promise<ConfigurationRevision[]> {
  const { data } = await api.get<ConfigurationRevision[]>(
    `/admin/configurations/${configurationId}/revisions`,
  )
  return data || []
}

export async function getRevision(
  configurationId: string,
  revisionId: string,
): Promise<ConfigurationRevision> {
  const { data } = await api.get<ConfigurationRevision>(
    `/admin/configurations/${configurationId}/revisions/${revisionId}`,
  )
  return data
}
