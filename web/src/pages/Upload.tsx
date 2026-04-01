import { useMemo, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { resolveUploadCapabilities } from '@/features/composite-upload/config/resolveCompositeScenario'
import { CompositeUploadPanel } from '@/features/composite-upload/CompositeUploadPanel'
import { useProfile } from '@/hooks/useProfile'
import { useUIStore } from '@/store/useStore'
import { cn } from '@/lib/utils'
import {
  AlertTriangle,
  Camera,
  FileText,
  FolderUp,
  Image as ImageIcon,
} from 'lucide-react'

export function Upload() {
  const { tenantCode, templates, isLoading: profileLoading } = useProfile()
  const pairedBatchMode = useUIStore(state => state.pairedBatchMode)
  const capabilities = useMemo(
    () => resolveUploadCapabilities({ tenantCode, templates, pairedBatchMode }),
    [tenantCode, templates, pairedBatchMode],
  )
  const [requestedTab, setRequestedTab] = useState<string>(capabilities.compositeScenarios[0]?.scenarioKey || '')

  const availableTabs = useMemo(
    () => capabilities.compositeScenarios.map(scenario => scenario.scenarioKey),
    [capabilities.compositeScenarios],
  )
  const activeTab = availableTabs.includes(requestedTab)
    ? requestedTab
    : availableTabs[0] || ''
  const activeScenario = capabilities.compositeScenarios.find(
    scenario => scenario.scenarioKey === activeTab,
  )
  const showTabs = Boolean(tenantCode) && availableTabs.length > 1

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 px-4 sm:px-6 animate-fadeIn">
      <div>
        <h2 className="text-2xl font-bold text-text-primary">上传文档</h2>
        <p className="text-text-secondary mt-1">
          支持 PDF、PNG、JPG、TIFF、BMP 格式，最大 20MB
        </p>
      </div>

      {showTabs && (
        <div className="flex gap-2 border-b border-border-default pb-2 flex-wrap">
          {capabilities.canUseSingleUpload && (
            <button
              onClick={() => setRequestedTab('single')}
              className={cn(
                'px-4 py-2 text-sm rounded-t-lg transition-colors',
                activeTab === 'single'
                  ? 'bg-primary-500/10 text-primary-400 border-b-2 border-primary-500'
                  : 'text-text-secondary hover:text-text-primary',
              )}
            >
              单文件上传
            </button>
          )}
          {capabilities.compositeScenarios.map(scenario => (
            <button
              key={scenario.scenarioKey}
              onClick={() => setRequestedTab(scenario.scenarioKey)}
              className={cn(
                'px-4 py-2 text-sm rounded-t-lg transition-colors flex items-center gap-1',
                activeTab === scenario.scenarioKey
                  ? 'bg-primary-500/10 text-primary-400 border-b-2 border-primary-500'
                  : 'text-text-secondary hover:text-text-primary',
              )}
            >
              <FolderUp className="h-4 w-4" />
              {scenario.displayName}
            </button>
          ))}
        </div>
      )}

      {!tenantCode && !profileLoading && (
        <Card className="border-warning-500/50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3 text-warning-500">
              <AlertTriangle className="h-6 w-6 flex-shrink-0" />
              <div>
                <p className="font-medium">请先选择所属部门</p>
                <p className="text-sm text-text-muted mt-1">
                  在设置页面选择您的所属部门后，即可使用文档上传功能
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {tenantCode && capabilities.compositeScenarios.length === 0 && !profileLoading && (
        <Card className="border-warning-500/50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3 text-warning-500">
              <AlertTriangle className="h-6 w-6 flex-shrink-0" />
              <div>
                <p className="font-medium">当前部门暂无可用上传能力</p>
                <p className="text-sm text-text-muted mt-1">
                  请先在后台配置可用模板或组合上传场景后再试。
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {tenantCode && activeScenario && (
        <CompositeUploadPanel scenario={activeScenario} />
      )}

      <Card className="bg-bg-secondary/50">
        <CardContent className="pt-6">
          <ul className="space-y-2 text-sm text-text-secondary">
            <li className="flex items-start gap-2">
              <ImageIcon className="h-4 w-4 mt-0.5 text-primary-400" />
              <span>上传清晰的文档图片或PDF文件，确保文字清晰可读</span>
            </li>
            <li className="flex items-start gap-2">
              <Camera className="h-4 w-4 mt-0.5 text-primary-400" />
              <span>移动端可直接使用相机拍照，建议在良好光线下拍摄</span>
            </li>
            <li className="flex items-start gap-2">
              <FileText className="h-4 w-4 mt-0.5 text-primary-400" />
              <span>
                {tenantCode
                  ? '根据当前部门已配置的批处理场景进行上传与识别'
                  : '请先选择所属部门'}
              </span>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
