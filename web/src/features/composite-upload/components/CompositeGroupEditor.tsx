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

const isMobile = typeof window !== 'undefined' && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
const FILE_ACCEPT = isMobile ? 'image/*,application/pdf' : '.pdf,.png,.jpg,.jpeg,.tiff,.bmp'

interface CompositeGroupEditorProps {
  scenario: CompositeScenarioConfig
  groups: CompositeGroup[]
  groupErrors?: Record<string, string[]>
  disabled?: boolean
  showTemplateSelector?: boolean
  renderGroupAside?: (group: CompositeGroup, index: number) => ReactNode
  onAddGroup: () => void
  onUpdateGroupTemplateSelection: (groupId: string, slotKey: CompositeSlotKey, templateId: string | null) => void
  onUpdateGroupFile: (groupId: string, slotKey: CompositeSlotKey, files: File[]) => void
  onRemoveGroupFile: (groupId: string, slotKey: CompositeSlotKey, fileId: string) => void
  onRemoveGroup?: (groupId: string) => void
}

function FileSlot({
  title,
  templateValue,
  templateOptions,
  files,
  disabled,
  showTemplateSelector,
  allowMultiple,
  leadingAction,
  onTemplateChange,
  onSelectFiles,
  onRemoveFile,
  onClear,
}: {
  title: string
  templateValue: string | null
  templateOptions: CompositeScenarioConfig['templateOptions']
  files: CompositeUploadedFile[]
  disabled: boolean
  showTemplateSelector: boolean
  allowMultiple: boolean
  leadingAction?: ReactNode
  onTemplateChange: (templateId: string | null) => void
  onSelectFiles: (files: File[]) => void
  onRemoveFile: (fileId: string) => void
  onClear: () => void
}) {
  const compactTitle = title.replace(/^文档\s*/u, '').replace(/\s+/g, '')
  return (
    <div className="space-y-2">
      {showTemplateSelector && (
        <div className="flex items-center gap-1">
          {leadingAction ? (
            <div className="flex shrink-0 items-center">{leadingAction}</div>
          ) : null}
          <select
            value={templateValue || ''}
            disabled={disabled}
            onChange={(event) => onTemplateChange(event.target.value || null)}
            className="h-8 min-w-0 flex-1 rounded-md border border-border-default bg-bg-primary px-2.5 text-xs text-text-primary"
          >
            <option value="">选择{compactTitle}文档类型...</option>
            {templateOptions.map(option => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
          <div className="flex shrink-0 items-center gap-1">
            {files.length > 0 && (
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
        <div className="flex items-center gap-2">
          {leadingAction ? (
            <div className="flex shrink-0 items-center">{leadingAction}</div>
          ) : null}
          <Label className="min-w-0 flex-1 text-xs text-text-secondary">{title}</Label>
          <div className="flex shrink-0 items-center gap-1">
            {files.length > 0 && (
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
          accept={FILE_ACCEPT}
          multiple={allowMultiple}
          className="hidden"
          disabled={disabled}
          onChange={(e) => {
            onSelectFiles(Array.from(e.target.files || []))
            e.currentTarget.value = ''
          }}
        />

        {files.length > 0 ? (
          <div className="rounded-md border border-border-default bg-bg-secondary px-2.5 py-2 transition-colors hover:border-primary-500/50 hover:bg-bg-hover/60 space-y-2">
            {files.map((file) => (
              <div key={file.id} className="flex items-center gap-2">
                <div className="h-8 w-8 rounded bg-bg-hover flex items-center justify-center overflow-hidden flex-shrink-0">
                  {file.preview ? (
                    <img src={file.preview} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <FileText className="h-3.5 w-3.5 text-text-muted" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="break-all text-xs text-text-primary leading-snug">{file.file.name}</p>
                  <p className="text-[11px] text-text-muted">{formatFileSize(file.file.size)}</p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={(event) => {
                    event.preventDefault()
                    onRemoveFile(file.id)
                  }}
                  disabled={disabled}
                  className="h-6 px-1.5 text-[11px] text-text-muted hover:text-error-500"
                >
                  移除
                </Button>
              </div>
            ))}
            <p className="text-[11px] text-text-muted">{allowMultiple ? '点击可继续追加文件' : '点击文件可替换'}</p>
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
  onRemoveGroupFile,
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
                    files={group.documents[slot.slotKey]}
                    disabled={disabled}
                    showTemplateSelector={showTemplateSelector}
                    allowMultiple={scenario.slotDefinitions.length === 1}
                    leadingAction={onRemoveGroup && slotIndex === 0 ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label="删除当前分组"
                        className="h-7 w-7 text-error-400 hover:bg-error-500/10 hover:text-error-500"
                        onClick={() => onRemoveGroup(group.id)}
                        disabled={disabled}
                      >
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    ) : undefined}
                    onTemplateChange={(templateId) => onUpdateGroupTemplateSelection(group.id, slot.slotKey, templateId)}
                    onSelectFiles={(files) => onUpdateGroupFile(group.id, slot.slotKey, files)}
                    onRemoveFile={(fileId) => onRemoveGroupFile(group.id, slot.slotKey, fileId)}
                    onClear={() => onUpdateGroupFile(group.id, slot.slotKey, [])}
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
