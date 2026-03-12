import { api } from './api'
import type {
  AdminTemplate,
  TemplateField,
  TemplateExample,
  CreateFieldPayload,
  UpdateFieldPayload,
  CreateExamplePayload,
  UpdateExamplePayload,
  UpdateTemplateConfigPayload,
  ReorderItem,
} from '@/types'

// ============ 模板 ============

export async function fetchAdminTemplates(tenantId?: string): Promise<AdminTemplate[]> {
  const params = tenantId ? { tenant_id: tenantId } : {}
  const { data } = await api.get<AdminTemplate[]>('/admin/templates', { params })
  return data || []
}

export async function updateTemplateConfig(
  templateId: string,
  payload: UpdateTemplateConfigPayload,
): Promise<AdminTemplate> {
  const { data } = await api.put<{ success: boolean; data: AdminTemplate }>(
    `/admin/templates/${templateId}`,
    payload,
  )
  return data.data
}

// ============ 字段 ============

export async function fetchFields(templateId: string): Promise<TemplateField[]> {
  const { data } = await api.get<TemplateField[]>(`/admin/templates/${templateId}/fields`)
  return data || []
}

export async function createField(
  templateId: string,
  payload: CreateFieldPayload,
): Promise<TemplateField> {
  const { data } = await api.post<{ success: boolean; data: TemplateField }>(
    `/admin/templates/${templateId}/fields`,
    payload,
  )
  return data.data
}

export async function updateField(
  fieldId: string,
  payload: UpdateFieldPayload,
): Promise<TemplateField> {
  const { data } = await api.put<{ success: boolean; data: TemplateField }>(
    `/admin/fields/${fieldId}`,
    payload,
  )
  return data.data
}

export async function deleteField(fieldId: string, force = false): Promise<void> {
  await api.delete(`/admin/fields/${fieldId}`, { params: force ? { force: true } : {} })
}

export async function reorderFields(
  templateId: string,
  items: ReorderItem[],
): Promise<void> {
  await api.put(`/admin/templates/${templateId}/fields/reorder`, { items })
}

// ============ Few-shot 示例 ============

export async function fetchExamples(templateId: string): Promise<TemplateExample[]> {
  const { data } = await api.get<TemplateExample[]>(
    `/admin/templates/${templateId}/examples`,
    { params: { active_only: false } },
  )
  return data || []
}

export async function createExample(
  templateId: string,
  payload: CreateExamplePayload,
): Promise<TemplateExample> {
  const { data } = await api.post<{ success: boolean; data: TemplateExample }>(
    `/admin/templates/${templateId}/examples`,
    payload,
  )
  return data.data
}

export async function updateExample(
  exampleId: string,
  payload: UpdateExamplePayload,
): Promise<TemplateExample> {
  const { data } = await api.put<{ success: boolean; data: TemplateExample }>(
    `/admin/examples/${exampleId}`,
    payload,
  )
  return data.data
}

export async function deleteExample(exampleId: string): Promise<void> {
  await api.delete(`/admin/examples/${exampleId}`)
}
