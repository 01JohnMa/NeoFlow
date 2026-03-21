import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import {
  X,
  Plus,
  Link2,
  AlertCircle,
} from 'lucide-react'
import type { Template } from '@/store/useStore'

interface UploadedFile {
  id: string
  file: File
  documentId?: string
  filePath?: string
  preview: string | null
}

interface MergePair {
  id: string
  fileA: UploadedFile | null
  fileB: UploadedFile | null
  templateIdA: string
  templateIdB: string
}

interface BatchMergePairingProps {
  allTemplates: Template[]
  unpairedFiles: UploadedFile[]
  pairs: MergePair[]
  onCreatePair: (pair: MergePair) => void
  onRemovePair: (pairId: string) => void
}

export function BatchMergePairing({
  allTemplates,
  unpairedFiles,
  onCreatePair,
  onRemovePair,
  pairs,
}: BatchMergePairingProps) {
  const [selectedFileA, setSelectedFileA] = useState<string>('')
  const [selectedFileB, setSelectedFileB] = useState<string>('')
  const [selectedTemplateIdA, setSelectedTemplateIdA] = useState<string>('')
  const [selectedTemplateIdB, setSelectedTemplateIdB] = useState<string>('')
  const [error, setError] = useState<string | null>(null)

  const handleCreatePair = () => {
    if (!selectedFileA || !selectedFileB) {
      setError('请选择两个文件进行配对')
      return
    }
    if (selectedFileA === selectedFileB) {
      setError('不能选择同一个文件')
      return
    }
    if (!selectedTemplateIdA || !selectedTemplateIdB) {
      setError('请为两个文件分别选择模板')
      return
    }

    const fileA = unpairedFiles.find(f => f.id === selectedFileA)
    const fileB = unpairedFiles.find(f => f.id === selectedFileB)
    if (!fileA || !fileB) {
      setError('所选文件不可用')
      return
    }

    setError(null)
    onCreatePair({
      id: `pair-${Date.now()}`,
      fileA,
      fileB,
      templateIdA: selectedTemplateIdA,
      templateIdB: selectedTemplateIdB,
    })

    setSelectedFileA('')
    setSelectedFileB('')
    setSelectedTemplateIdA('')
    setSelectedTemplateIdB('')
  }

  if (unpairedFiles.length < 2 && pairs.length === 0) {
    return null
  }

  return (
    <div className="space-y-4">
      {/* 已配对列表 */}
      {pairs.length > 0 && (
        <div className="space-y-2">
          <Label className="text-sm font-medium text-text-secondary">已配对</Label>
          {pairs.map(pair => {
            const tplA = allTemplates.find(t => t.id === pair.templateIdA)
            const tplB = allTemplates.find(t => t.id === pair.templateIdB)
            return (
              <div
                key={pair.id}
                className="flex items-center gap-3 p-3 rounded-lg bg-bg-secondary border border-border-default"
              >
                <Link2 className="h-4 w-4 text-accent-400 flex-shrink-0" />
                <div className="flex-1 min-w-0 text-sm">
                  <span className="text-text-primary truncate">
                    {pair.fileA?.file.name}
                  </span>
                  <Badge variant="outline" className="mx-1 text-xs">
                    {tplA?.name || pair.templateIdA}
                  </Badge>
                  <span className="text-text-muted mx-1">+</span>
                  <span className="text-text-primary truncate">
                    {pair.fileB?.file.name}
                  </span>
                  <Badge variant="outline" className="mx-1 text-xs">
                    {tplB?.name || pair.templateIdB}
                  </Badge>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-text-muted hover:text-error-500"
                  onClick={() => onRemovePair(pair.id)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )
          })}
        </div>
      )}

      {/* 新建配对 */}
      {unpairedFiles.length >= 2 && (
        <div className="space-y-3 p-4 rounded-lg border border-dashed border-border-default">
          <Label className="text-sm font-medium text-text-secondary">新建配对</Label>

          <div className="grid grid-cols-2 gap-3">
            {/* 文件 A */}
            <div className="space-y-1">
              <label className="text-xs text-text-muted">文件 A</label>
              <select
                value={selectedFileA}
                onChange={e => setSelectedFileA(e.target.value)}
                className="w-full rounded-md border border-border-default bg-bg-primary px-3 py-2 text-sm"
              >
                <option value="">选择文件...</option>
                {unpairedFiles
                  .filter(f => f.id !== selectedFileB)
                  .map(f => (
                    <option key={f.id} value={f.id}>{f.file.name}</option>
                  ))}
              </select>
              <select
                value={selectedTemplateIdA}
                onChange={e => setSelectedTemplateIdA(e.target.value)}
                className="w-full rounded-md border border-border-default bg-bg-primary px-3 py-2 text-sm"
              >
                <option value="">选择模板...</option>
                {allTemplates.map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>

            {/* 文件 B */}
            <div className="space-y-1">
              <label className="text-xs text-text-muted">文件 B</label>
              <select
                value={selectedFileB}
                onChange={e => setSelectedFileB(e.target.value)}
                className="w-full rounded-md border border-border-default bg-bg-primary px-3 py-2 text-sm"
              >
                <option value="">选择文件...</option>
                {unpairedFiles
                  .filter(f => f.id !== selectedFileA)
                  .map(f => (
                    <option key={f.id} value={f.id}>{f.file.name}</option>
                  ))}
              </select>
              <select
                value={selectedTemplateIdB}
                onChange={e => setSelectedTemplateIdB(e.target.value)}
                className="w-full rounded-md border border-border-default bg-bg-primary px-3 py-2 text-sm"
              >
                <option value="">选择模板...</option>
                {allTemplates.map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 text-error-500 text-xs">
              <AlertCircle className="h-3 w-3" />
              <span>{error}</span>
            </div>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={handleCreatePair}
            className="w-full"
          >
            <Plus className="h-4 w-4 mr-1" />
            确认配对
          </Button>
        </div>
      )}
    </div>
  )
}

export type { UploadedFile, MergePair }
