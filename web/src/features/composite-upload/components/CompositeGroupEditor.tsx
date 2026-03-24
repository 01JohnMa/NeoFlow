import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
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
  groupCustomPushNames?: Record<string, string>
  groupEffectivePushNames?: Record<string, string>
  disabled?: boolean
  onAddGroup: () => void
  onUpdateGroupFile: (groupId: string, slotKey: CompositeSlotKey, file: File | null) => void
  onUpdateGroupCustomPushName: (groupId: string, value: string) => void
  onApplyGroupRecommendedName: (groupId: string) => void
  onRemoveGroup: (groupId: string) => void
}

type GroupStatus = 'empty' | 'complete' | 'partial'

function getGroupStatus(group: CompositeGroup, scenario: CompositeScenarioConfig): GroupStatus {
  const slotCount = scenario.slotDefinitions.length
  const filledCount = scenario.slotDefinitions.filter(slot => group.documents[slot.slotKey]).length

  if (filledCount === 0) return 'empty'
  if (filledCount === slotCount) return 'complete'
  return 'partial'
}

function getGroupStatusMeta(status: GroupStatus) {
  switch (status) {
    case 'complete':
      return {
        label: '完整组',
        className: 'border-success-500/40 text-success-500',
      }
    case 'partial':
      return {
        label: '部分组',
        className: 'border-primary-500/40 text-primary-400',
      }
    default:
      return {
        label: '空组',
        className: 'border-border-default text-text-muted',
      }
  }
}

function FileSlot({
  title,
  file,
  disabled,
  onSelect,
  onClear,
}: {
  title: string
  file: CompositeUploadedFile | null
  disabled: boolean
  onSelect: (file: File | null) => void
  onClear: () => void
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs text-text-secondary">{title}</Label>
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
  groupCustomPushNames = {},
  groupEffectivePushNames = {},
  disabled = false,
  onAddGroup,
  onUpdateGroupFile,
  onUpdateGroupCustomPushName,
  onApplyGroupRecommendedName,
  onRemoveGroup,
}: CompositeGroupEditorProps) {
  return (
    <div className="space-y-3">
      <div>
        <Label className="text-sm font-medium text-text-secondary">组合分组</Label>
        <p className="mt-1 text-xs text-text-muted">
          按组上传多个关联文档，点击已上传文件可直接替换。
        </p>
      </div>

      {groups.map((group, index) => {
        const status = getGroupStatus(group, scenario)
        const statusMeta = getGroupStatusMeta(status)
        const errors = groupErrors[group.id] || []

        return (
          <div
            key={group.id}
            className="space-y-3 rounded-lg border border-border-default bg-bg-primary p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-text-primary">分组 {index + 1}</span>
                <Badge variant="outline" className={statusMeta.className}>
                  {statusMeta.label}
                </Badge>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-text-muted hover:text-error-500"
                onClick={() => onRemoveGroup(group.id)}
                disabled={disabled}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className={`grid gap-2.5 ${scenario.slotDefinitions.length > 1 ? 'md:grid-cols-2' : ''}`}>
              {scenario.slotDefinitions.map(slot => (
                <FileSlot
                  key={`${group.id}-${slot.slotKey}`}
                  title={slot.label}
                  file={group.documents[slot.slotKey]}
                  disabled={disabled}
                  onSelect={(file) => onUpdateGroupFile(group.id, slot.slotKey, file)}
                  onClear={() => onUpdateGroupFile(group.id, slot.slotKey, null)}
                />
              ))}
            </div>

            <div className="space-y-2 rounded-md border border-border-default/70 p-2.5">
              <div className="flex items-center justify-between gap-3">
                <Label className="text-xs text-text-secondary">当前组自定义文件名</Label>
                {!disabled && groupEffectivePushNames[group.id] && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-6 px-1.5 text-[11px] text-text-muted"
                    onClick={() => onApplyGroupRecommendedName(group.id)}
                  >
                    使用推荐文件名
                  </Button>
                )}
              </div>
              <Input
                value={groupCustomPushNames[group.id] || ''}
                onChange={(e) => onUpdateGroupCustomPushName(group.id, e.target.value)}
                placeholder={groupEffectivePushNames[group.id] || '请先在该组上传文件'}
                maxLength={100}
                disabled={disabled}
                className="h-8 text-xs"
              />
              <div className="text-[11px] text-text-muted">
                实际生效名称：{groupEffectivePushNames[group.id] || '未生成'}
              </div>
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
        )
      })}
    </div>
  )
}
