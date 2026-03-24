import type { Template } from '@/store/useStore'

export function resolveSelectedSingleTemplateId(
  templates: Template[],
  selectedTemplateId: string | null,
): string | null {
  const activeTemplates = templates.filter(template => template.is_active !== false)

  if (activeTemplates.length === 1) {
    return activeTemplates[0]?.id || null
  }

  if (selectedTemplateId && activeTemplates.some(template => template.id === selectedTemplateId)) {
    return selectedTemplateId
  }

  return null
}
