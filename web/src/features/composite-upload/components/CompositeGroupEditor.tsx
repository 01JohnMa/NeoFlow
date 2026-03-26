import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { formatFileSize } from '@/lib/utils'
import type { CompositeGroup, CompositeScenarioConfig, CompositeSlotKey, CompositeUploadedFile } from '@/features/composite-upload/core/types'
import {
  AlertCircle,
  FileText,
  Plus,
  Upload,
  X,
} from 'lucide-react'

interface CompositeGroupEditorProps {
  scenario: CompositeScenarioConfig
  groups: CompositeGroup[]
  groupErrors?: Record<string, string[]>
  disabled?: boolean
  showTemplateSelector?: boolean
  renderGroupAside?: (group: CompositeGroup, index: number) => ReactNode
  onAddGroup: () => void
  onUpdateGroupTemplateSelection: (groupId: string, slotKey: CompositeSlotKey, templateId: string | null) => void
  onUpdateGroupFile: (groupId: string, slotKey: CompositeSlotKey, file: File | null) => void
  onRemoveGroup?: (groupId: string) => void
}

function FileSlot({
  title,
  templateValue,
  templateOptions,
  file,
  disabled,
  showTemplateSelector,
  trailingAction,
  onTemplateChange,
  onSelect,
  onClear,
}: {
  title: string
  templateValue: string | null
  templateOptions: CompositeScenarioConfig['templateOptions']
  file: CompositeUploadedFile | null
  disabled: boolean
  showTemplateSelector: boolean
  trailingAction?: ReactNode
  onTemplateChange: (templateId: string | null) => void
  onSelect: (file: File | null) => void
  onClear: () => void
}) {
  const compactTitle = title.replace(/^文档\s*/u, '').replace(/\s+/g, '')
  return (
    <div className="space-y-2">
      {showTemplateSelector && (
        <div className="flex items-center gap-1">
          <select
            value={templateValue || ''}
            disabled={disabled}
            onChange={(event) => onTemplateChange(event.target.value || null)}
            className="h-8 w-full rounded-md border border-border-default bg-bg-primary px-2.5 text-xs text-text-primary"
          >
            <option value="">选择{compactTitle}文档类型...</option>
            {templateOptions.map(option => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
          <div className="flex items-center gap-1">
            {trailingAction}
            {file && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onClear}
                disabled={disabled}
                className="h-6 px-1.5 text-[11px] text-text-muted hover:text-error-500"
              >
                清空
              </Button>
            )}
          </div>
        </div>
      )}

      {!showTemplateSelector && (
        <div className="flex items-center justify-between gap-2">
          <Label className="text-xs text-text-secondary">{title}</Label>
          <div className="flex items-center gap-1">
            {trailingAction}
            {file && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onClear}
                disabled={disabled}
                className="h-6 px-1.5 text-[11px] text-text-muted hover:text-error-500"
              >
                清空
              </Button>
            )}
          </div>
        </div>
      )}

      <label className="block cursor-pointer">
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
          className="hidden"
          disabled={disabled}
          onChange={(e) => {
            onSelect(e.target.files?.[0] || null)
            e.currentTarget.value = ''
          }}
        />

        {file ? (
          <div className="rounded-md border border-border-default bg-bg-secondary px-2.5 py-2 transition-colors hover:border-primary-500/50 hover:bg-bg-hover/60">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded bg-bg-hover flex items-center justify-center overflow-hidden flex-shrink-0">
                {file.preview ? (
                  <img src={file.preview} alt="" className="h-full w-full object-cover" />
                ) : (
                  <FileText className="h-3.5 w-3.5 text-text-muted" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs text-text-primary">{file.file.name}</p>
                <p className="text-[11px] text-text-muted">{formatFileSize(file.file.size)} · 点击文件替换</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-border-default bg-bg-primary px-2.5 py-3 text-center text-xs text-text-secondary transition-colors hover:border-primary-500/50 hover:bg-bg-hover">
            <Upload className="mx-auto mb-1.5 h-4 w-4 text-text-muted" />
            <div>上传文件</div>
          </div>
        )}
      </label>
    </div>
  )
}

export function CompositeGroupEditor({
  scenario,
  groups,
  groupErrors = {},
  disabled = false,
  showTemplateSelector = true,
  renderGroupAside,
  onAddGroup,
  onUpdateGroupTemplateSelection,
  onUpdateGroupFile,
  onRemoveGroup,
}: CompositeGroupEditorProps) {
  return (
    <div className="space-y-3">
      {groups.map((group, index) => {
        const errors = groupErrors[group.id] || []

        return (
          <div
            key={group.id}
            className={renderGroupAside ? 'grid gap-2 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-start' : ''}
          >
            <div className="space-y-4 rounded-lg border border-border-default bg-bg-primary p-4">
              <div className={`grid gap-4 ${scenario.slotDefinitions.length > 1 ? 'lg:grid-cols-2' : ''}`}>
                {scenario.slotDefinitions.map((slot, slotIndex) => (
                  <FileSlot
                    key={`${group.id}-${slot.slotKey}`}
                    title={slot.label}
                    templateValue={group.templateSelections[slot.slotKey] || slot.templateId || null}
                    templateOptions={scenario.templateOptions}
                    file={group.documents[slot.slotKey]}
                    disabled={disabled}
                    showTemplateSelector={showTemplateSelector}
                    trailingAction={!renderGroupAside && onRemoveGroup && slotIndex === 0 ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label="删除当前分组"
                        className="h-6 w-6 text-error-400 hover:bg-error-500/10 hover:text-error-500"
                        onClick={() => onRemoveGroup(group.id)}
                        disabled={disabled}
                      >
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    ) : undefined}
                    onTemplateChange={(templateId) => onUpdateGroupTemplateSelection(group.id, slot.slotKey, templateId)}
                    onSelect={(file) => onUpdateGroupFile(group.id, slot.slotKey, file)}
                    onClear={() => onUpdateGroupFile(group.id, slot.slotKey, null)}
                  />
                ))}
              </div>

              {errors.length > 0 && (
                <div className="space-y-1.5 rounded-md border border-error-500/20 bg-error-500/10 p-2.5 text-xs text-error-500">
                  {errors.map(error => (
                    <div key={error} className="flex items-start gap-2">
                      <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                      <span>{error}</span>
                    </div>
                  ))}
                </div>
              )}

              {!disabled && index === groups.length - 1 && (
                <div className="flex justify-end pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={onAddGroup}
                    className="h-8 text-xs"
                  >
                    <Plus className="mr-1 h-3.5 w-3.5" />
                    新增一组
                  </Button>
                </div>
              )}
            </div>

            {renderGroupAside ? renderGroupAside(group, index) : null}
          </div>
        )
      })}
    </div>
  )
}
