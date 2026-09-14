import { useEffect, useState } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  Code2,
  FileText,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
  Wand2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import * as sdkApi from '@/services/sdk'
import type {
  SDKCommitResult,
  SDKConfirmTemplatePayload,
  SDKDetectedField,
  SDKDocumentAnalysis,
  SDKSession,
} from '@/types'
import { cn } from '@/lib/utils'

interface AiTemplateWizardProps {
  tenantId: string
  tenantName?: string
  initialSessionId?: string | null
  onSessionChange?: (sessionId: string | null) => void
  onCommitted: (configurationId: string) => void | Promise<void>
}

const steps = [
  { key: 'upload', label: '上传样例' },
  { key: 'analyze', label: 'AI 分析' },
  { key: 'confirm', label: '确认配置' },
  { key: 'commit', label: '发布配置' },
]

const parseAllowedValues = (value: string): string[] | null => {
  const values = value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
  return values.length > 0 ? values : null
}

const createEmptyField = (index: number): SDKDetectedField => ({
  field_key: `field_${index + 1}`,
  field_label: '新字段',
  field_type: 'text',
  extraction_hint: '',
  review_enforced: false,
  review_allowed_values: null,
  sample_value: null,
})

export function AiTemplateWizard({
  tenantId,
  tenantName,
  initialSessionId,
  onSessionChange,
  onCommitted,
}: AiTemplateWizardProps) {
  const [file, setFile] = useState<File | null>(null)
  const [excelTemplateFile, setExcelTemplateFile] = useState<File | null>(null)
  const [session, setSession] = useState<SDKSession | null>(null)
  const [analysis, setAnalysis] = useState<SDKDocumentAnalysis | null>(null)
  const [fields, setFields] = useState<SDKDetectedField[]>([])
  const [templateName, setTemplateName] = useState('')
  const [templateCode, setTemplateCode] = useState('')
  const [parseMode, setParseMode] = useState<'pipeline' | 'vlm'>('pipeline')
  const [instruction, setInstruction] = useState('')
  const [description, setDescription] = useState('')
  const [perPageExtraction, setPerPageExtraction] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [cleanerCode, setCleanerCode] = useState('')
  const [configRevision, setConfigRevision] = useState(0)
  const [promptRevision, setPromptRevision] = useState<number | null>(null)
  const [codeRevision, setCodeRevision] = useState<number | null>(null)
  const [commitResult, setCommitResult] = useState<SDKCommitResult | null>(null)
  const [loadingAction, setLoadingAction] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const activeStep = commitResult ? 'commit' : analysis ? 'confirm' : session ? 'analyze' : 'upload'
  const fieldKeys = fields.map((field) => field.field_key.trim()).filter(Boolean)
  const hasFieldErrors = fields.some(
    (field) => !field.field_key.trim() || !field.field_label.trim(),
  )
  const hasDuplicateFieldKeys = fieldKeys.length !== new Set(fieldKeys).size
  const promptIsCurrent = promptRevision === configRevision
  const codeIsCurrent = codeRevision === configRevision
  const canCommit = Boolean(
    session
      && fields.length > 0
      && !hasFieldErrors
      && !hasDuplicateFieldKeys,
  )

  const validationMessage = (() => {
    if (!analysis) return null
    if (fields.length === 0) return '至少需要 1 个识别字段'
    if (hasFieldErrors) return '字段键名和标签不能为空'
    if (hasDuplicateFieldKeys) return '字段键名不能重复'
    return null
  })()

  const markConfigChanged = () => {
    setConfigRevision((revision) => revision + 1)
  }

  const resetGeneratedArtifacts = () => {
    setPrompt('')
    setCleanerCode('')
    setPromptRevision(null)
    setCodeRevision(null)
  }

  const resetAnalysisState = () => {
    setAnalysis(null)
    setFields([])
    setDescription('')
    setPerPageExtraction(false)
    setConfigRevision(0)
    resetGeneratedArtifacts()
    setCommitResult(null)
  }

  const runAction = async (name: string, action: () => Promise<void>) => {
    setLoadingAction(name)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setLoadingAction(null)
    }
  }

  const handleCreateSession = () => {
    if (!file || !templateName.trim() || !templateCode.trim()) return
    void runAction('upload', async () => {
      const created = await sdkApi.createSDKSession(file, excelTemplateFile, {
        tenantId,
        templateName: templateName.trim(),
        templateCode: templateCode.trim(),
        parseMode,
        instruction,
      })
      setSession(created)
      onSessionChange?.(created.id)
      resetAnalysisState()
    })
  }

  const handleRetryParse = () => {
    if (!session) return
    void runAction('retry-parse', async () => {
      const updated = await sdkApi.retrySDKParse(session.id)
      setSession(updated)
      onSessionChange?.(updated.id)
    })
  }

  const sessionId = session?.id
  const sessionState = session?.state

  // 刷新页面或服务重启后，按 URL 中的会话 id 恢复解析状态
  useEffect(() => {
    if (!initialSessionId || session) return
    let cancelled = false
    sdkApi
      .getSDKSession(initialSessionId)
      .then((restored) => {
        if (cancelled) return
        setSession(restored)
        setTemplateName((value) => value || restored.template_name)
        setTemplateCode((value) => value || restored.template_code)
        setParseMode(restored.parse_mode)
        setInstruction((value) => value || restored.instruction || '')
      })
      .catch(() => {
        if (!cancelled) setError('会话已失效，请重新上传样例')
      })
    return () => {
      cancelled = true
    }
  }, [initialSessionId, session])

  useEffect(() => {
    if (!sessionId || sessionState !== 'parsing') return
    const timer = window.setInterval(() => {
      sdkApi
        .getSDKSession(sessionId)
        .then((updated) => setSession(updated))
        .catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [sessionId, sessionState])

  const handleAnalyze = () => {
    if (!session) return
    void runAction('analyze', async () => {
      const result = await sdkApi.analyzeSDKSession(session.id)
      setAnalysis(result)
      setFields(result.detected_fields)
      setDescription(`由 AI 根据 ${session.file_name} 建议字段`)
      setPerPageExtraction(false)
      setConfigRevision((revision) => revision + 1)
      resetGeneratedArtifacts()
      setCommitResult(null)
    })
  }

  const buildConfirmPayload = (): SDKConfirmTemplatePayload => ({
    template_name: (templateName || session?.template_name || '').trim(),
    template_code: (templateCode || session?.template_code || '').trim(),
    description: description.trim() || null,
    per_page_extraction: perPageExtraction,
    fields: fields.map((field) => ({
      ...field,
      field_key: field.field_key.trim(),
      field_label: field.field_label.trim(),
      extraction_hint: field.extraction_hint.trim(),
      review_allowed_values: field.review_allowed_values?.length ? field.review_allowed_values : null,
    })),
  })

  const confirmCurrentTemplate = async () => {
    if (!session) return
    await sdkApi.confirmSDKTemplate(session.id, buildConfirmPayload())
  }

  const handleGeneratePrompt = () => {
    if (!session || !canCommit) return
    void runAction('prompt', async () => {
      await confirmCurrentTemplate()
      const generated = await sdkApi.generateSDKPrompt(session.id)
      setPrompt(generated)
      setPromptRevision(configRevision)
    })
  }

  const handleGenerateCode = () => {
    if (!session || !canCommit) return
    void runAction('code', async () => {
      await confirmCurrentTemplate()
      const generated = await sdkApi.generateSDKCode(session.id)
      setCleanerCode(generated)
      setCodeRevision(configRevision)
    })
  }

  const handleCommit = () => {
    if (!session || !canCommit) return
    void runAction('commit', async () => {
      await confirmCurrentTemplate()
      let finalPrompt = prompt
      if (!finalPrompt.trim() || !promptIsCurrent) {
        finalPrompt = await sdkApi.generateSDKPrompt(session.id)
        setPrompt(finalPrompt)
        setPromptRevision(configRevision)
      }
      const result = await sdkApi.commitSDKSession(session.id, {
        prompt: finalPrompt,
        cleaner_code: codeIsCurrent ? cleanerCode || null : null,
      })
      setCommitResult(result)
      await onCommitted(result.configuration_id)
    })
  }

  const updateTemplateField = (patch: {
    description?: string
    perPageExtraction?: boolean
  }) => {
    if (patch.description !== undefined) setDescription(patch.description)
    if (patch.perPageExtraction !== undefined) setPerPageExtraction(patch.perPageExtraction)
    markConfigChanged()
  }

  const updateField = (index: number, patch: Partial<SDKDetectedField>) => {
    setFields((prev) => prev.map((field, i) => (i === index ? { ...field, ...patch } : field)))
    markConfigChanged()
  }

  const moveField = (index: number, direction: 'up' | 'down') => {
    setFields((prev) => {
      const swapIndex = direction === 'up' ? index - 1 : index + 1
      if (swapIndex < 0 || swapIndex >= prev.length) return prev
      const next = [...prev]
      ;[next[index], next[swapIndex]] = [next[swapIndex], next[index]]
      return next
    })
    markConfigChanged()
  }

  const addField = () => {
    setFields((prev) => [...prev, createEmptyField(prev.length)])
    markConfigChanged()
  }

  const removeField = (index: number) => {
    setFields((prev) => prev.filter((_, i) => i !== index))
    markConfigChanged()
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {steps.map((step) => (
          <div
            key={step.key}
            className={cn(
              'flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium',
              activeStep === step.key
                ? 'border-primary-500/40 bg-primary-500/10 text-primary-300'
                : 'border-border-default text-text-muted',
            )}
          >
            {commitResult && step.key === 'commit' ? <Check className="h-3.5 w-3.5" /> : null}
            {step.label}
          </div>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-error-500/30 bg-error-500/10 px-4 py-3 text-sm text-error-500">
          {error}
        </div>
      )}

      {validationMessage && (
        <div className="rounded-lg border border-warning-500/30 bg-warning-500/10 px-4 py-3 text-sm text-warning-400">
          {validationMessage}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="space-y-4">
          <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-text-primary">
              <Upload className="h-4 w-4 text-primary-400" />
              待识别图片/文档
            </div>
            <p className="mb-3 text-xs leading-relaxed text-text-muted">
              第一步先确定模板归属与身份：上传需要解析的图片或文档，AI 只负责建议字段。
            </p>

            <div className="mb-3 rounded-lg border border-border-default bg-bg-card p-3">
              <p className="text-xs text-text-muted">
                所属租户：<span className="text-text-primary">{tenantName || tenantId}</span>
              </p>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div>
                  <Label>文档类型名称</Label>
                  <Input
                    className="mt-1"
                    value={templateName}
                    placeholder="例如：检测报告"
                    disabled={Boolean(session)}
                    onChange={(e) => setTemplateName(e.target.value)}
                  />
                </div>
                <div>
                  <Label>文档类型编码</Label>
                  <Input
                    className="mt-1"
                    value={templateCode}
                    placeholder="例如：inspection_report"
                    disabled={Boolean(session)}
                    onChange={(e) => setTemplateCode(e.target.value)}
                  />
                </div>
                <div>
                  <Label>解析模式</Label>
                  <Select
                    className="mt-1"
                    value={parseMode}
                    disabled={Boolean(session)}
                    onChange={(e) => setParseMode(e.target.value as 'pipeline' | 'vlm')}
                  >
                    <option value="pipeline">快速解析</option>
                    <option value="vlm">高精度解析</option>
                  </Select>
                </div>
                <div>
                  <Label>字段建议说明（可选）</Label>
                  <Input
                    className="mt-1"
                    value={instruction}
                    placeholder="例如：重点抽金额与日期"
                    disabled={Boolean(session)}
                    onChange={(e) => setInstruction(e.target.value)}
                  />
                </div>
              </div>
            </div>

            <Input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null)
                setSession(null)
                onSessionChange?.(null)
                resetAnalysisState()
              }}
            />
            <div className="mt-4 rounded-lg border border-border-default bg-bg-card p-3">
              <Label>空 Excel 填报模板（可选）</Label>
              <p className="mb-2 mt-1 text-xs leading-relaxed text-text-muted">
                模板只放 <span className="font-mono">{'{{field_key}}'}</span> 槽位；系统会扫描槽位，再把上方文件的解析结果填进去。
              </p>
              <Input
                type="file"
                accept=".xlsx,.xlsm"
                onChange={(event) => {
                  setExcelTemplateFile(event.target.files?.[0] ?? null)
                  setSession(null)
                  onSessionChange?.(null)
                  resetAnalysisState()
                }}
              />
              {excelTemplateFile && (
                <p className="mt-2 text-xs text-text-muted">
                  已选择：{excelTemplateFile.name}
                </p>
              )}
            </div>
            <Button
              className="mt-3"
              size="sm"
              onClick={handleCreateSession}
              disabled={!file || !templateName.trim() || !templateCode.trim()}
              loading={loadingAction === 'upload'}
            >
              上传并解析
            </Button>
          </div>

          {session && (
            <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-medium text-text-primary">
                <FileText className="h-4 w-4 text-primary-400" />
                解析状态
              </div>
              <p className="text-xs text-text-muted">{session.file_name}</p>
              <p className="mt-1 text-xs text-text-muted">
                解析模式：{session.parse_mode === 'vlm' ? '高精度解析' : '快速解析'}
              </p>

              {session.state === 'parsing' && (
                <div className="mt-3">
                  <div className="h-2 w-full overflow-hidden rounded-full bg-bg-card">
                    <div
                      className="h-full rounded-full bg-primary-500 transition-all"
                      style={{ width: `${session.parse_progress ?? 5}%` }}
                    />
                  </div>
                  <p className="mt-2 text-xs text-text-muted">
                    MinerU 解析中，页面会自动刷新进度
                  </p>
                </div>
              )}

              {session.state === 'parsed' && (
                <p className="mt-3 text-xs text-success-500">解析完成，可以开始 AI 分析</p>
              )}

              {session.state === 'parse_failed' && (
                <div className="mt-3">
                  <p className="text-xs text-error-500">
                    {session.parse_error || '解析失败'}
                  </p>
                  <Button
                    className="mt-2"
                    size="sm"
                    variant="secondary"
                    onClick={handleRetryParse}
                    loading={loadingAction === 'retry-parse'}
                  >
                    <RefreshCw className="h-4 w-4" />
                    重试解析
                  </Button>
                </div>
              )}

              {session.excel_template_file_name && (
                <div className="mt-3 rounded-lg border border-border-default bg-bg-card p-3">
                  <p className="text-xs font-medium text-text-primary">
                    Excel 空模板：{session.excel_template_file_name}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {session.excel_placeholders.map((placeholder) => (
                      <span
                        key={`${placeholder.sheet_name}-${placeholder.coordinate}-${placeholder.field_key}`}
                        className="rounded-full border border-primary-500/30 bg-primary-500/10 px-2 py-1 font-mono text-xs text-primary-300"
                      >
                        {placeholder.field_key}
                      </span>
                    ))}
                  </div>
                  {session.excel_placeholders.length === 0 && (
                    <p className="mt-2 text-xs text-warning-400">
                      未扫描到 {'{{field_key}}'} 槽位，请检查空模板。
                    </p>
                  )}
                </div>
              )}
              <Button
                className="mt-3"
                size="sm"
                variant="secondary"
                onClick={handleAnalyze}
                disabled={session.state !== 'parsed'}
                loading={loadingAction === 'analyze'}
              >
                <Sparkles className="h-4 w-4" />
                分析文档
              </Button>
            </div>
          )}

          {analysis && (
            <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
              <div className="mb-2 text-sm font-medium text-text-primary">AI 字段建议</div>
              <div className="space-y-2 text-xs text-text-secondary">
                <p>已建议 {analysis.detected_fields.length} 个字段，可在右侧确认与调整</p>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          {analysis && (
            <>
              <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-text-primary">
                  <Wand2 className="h-4 w-4 text-primary-400" />
                  模板信息
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <p className="text-xs text-text-muted">文档类型</p>
                    <p className="mt-1 text-sm text-text-primary">
                      {templateName || session?.template_name}
                      <span className="ml-2 font-mono text-xs text-text-muted">
                        {templateCode || session?.template_code}
                      </span>
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-text-muted">解析模式</p>
                    <p className="mt-1 text-sm text-text-primary">
                      {(session?.parse_mode ?? parseMode) === 'vlm' ? '高精度解析' : '快速解析'}
                    </p>
                  </div>
                  <label className="flex items-end gap-2 pb-2 text-sm text-text-secondary">
                    <input
                      type="checkbox"
                      checked={perPageExtraction}
                      onChange={(e) => updateTemplateField({ perPageExtraction: e.target.checked })}
                    />
                    逐页提取
                  </label>
                </div>
                <Label className="mt-3 block">描述</Label>
                <Textarea
                  className="mt-1"
                  value={description}
                  onChange={(e) => updateTemplateField({ description: e.target.value })}
                />
              </div>

              <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-text-primary">识别字段</div>
                  <Button size="sm" variant="secondary" onClick={addField}>
                    <Plus className="h-4 w-4" />
                    新增字段
                  </Button>
                </div>
                <div className="space-y-3">
                  {fields.map((field, index) => (
                    <div
                      key={`${field.field_key}-${index}`}
                      className="rounded-lg border border-border-default p-3"
                    >
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <span className="text-xs font-medium text-text-muted">字段 {index + 1}</span>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => moveField(index, 'up')}
                            disabled={index === 0}
                          >
                            <ChevronUp className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => moveField(index, 'down')}
                            disabled={index === fields.length - 1}
                          >
                            <ChevronDown className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="hover:text-error-500"
                            onClick={() => removeField(index)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                      <div className="grid gap-2 md:grid-cols-[1fr_1fr_120px]">
                        <div>
                          <Label>字段标签</Label>
                          <Input
                            className="mt-1"
                            value={field.field_label}
                            onChange={(e) => updateField(index, { field_label: e.target.value })}
                          />
                        </div>
                        <div>
                          <Label>字段键名</Label>
                          <Input
                            className="mt-1 font-mono"
                            value={field.field_key}
                            onChange={(e) => updateField(index, { field_key: e.target.value })}
                          />
                        </div>
                        <div>
                          <Label>类型</Label>
                          <Select
                            className="mt-1"
                            value={field.field_type}
                            onChange={(e) => (
                              updateField(index, {
                                field_type: e.target.value as SDKDetectedField['field_type'],
                              })
                            )}
                          >
                            <option value="text">text</option>
                            <option value="date">date</option>
                            <option value="number">number</option>
                          </Select>
                        </div>
                        <div className="md:col-span-3">
                          <Label>提取提示</Label>
                          <Textarea
                            className="mt-1"
                            value={field.extraction_hint}
                            onChange={(e) => updateField(index, { extraction_hint: e.target.value })}
                          />
                        </div>
                        <label className="flex items-center gap-2 text-sm text-text-secondary">
                          <input
                            type="checkbox"
                            checked={field.review_enforced}
                            onChange={(e) => updateField(index, { review_enforced: e.target.checked })}
                          />
                          审核必填
                        </label>
                        <div className="md:col-span-2">
                          <Label>允许值</Label>
                          <Input
                            className="mt-1"
                            value={(field.review_allowed_values ?? []).join(', ')}
                            onChange={(e) => (
                              updateField(index, { review_allowed_values: parseAllowedValues(e.target.value) })
                            )}
                          />
                        </div>
                      </div>
                      {field.sample_value && (
                        <p className="mt-2 text-xs text-text-muted">样例值：{field.sample_value}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleGeneratePrompt}
                  disabled={!canCommit}
                  loading={loadingAction === 'prompt'}
                >
                  <Sparkles className="h-4 w-4" />
                  生成 Prompt
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleGenerateCode}
                  disabled={!canCommit}
                  loading={loadingAction === 'code'}
                >
                  <Code2 className="h-4 w-4" />
                  生成清洗代码
                </Button>
                <Button
                  size="sm"
                  onClick={handleCommit}
                  disabled={!canCommit}
                  loading={loadingAction === 'commit'}
                >
                  创建并发布配置
                </Button>
              </div>

              {prompt && (
                <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="text-sm font-medium text-text-primary">Prompt 预览</div>
                    {!promptIsCurrent && (
                      <span className="text-xs text-warning-400">配置已更新</span>
                    )}
                  </div>
                  <Textarea
                    className="min-h-[220px] font-mono text-xs"
                    value={prompt}
                    onChange={(e) => {
                      setPrompt(e.target.value)
                      setPromptRevision(configRevision)
                    }}
                  />
                </div>
              )}

              {cleanerCode && (
                <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="text-sm font-medium text-text-primary">清洗代码预览</div>
                    {!codeIsCurrent && (
                      <span className="text-xs text-warning-400">配置已更新</span>
                    )}
                  </div>
                  <Textarea
                    className="min-h-[220px] font-mono text-xs"
                    value={cleanerCode}
                    onChange={(e) => {
                      setCleanerCode(e.target.value)
                      setCodeRevision(configRevision)
                    }}
                  />
                </div>
              )}
            </>
          )}

          {commitResult && (
            <div className="rounded-lg border border-success-500/30 bg-success-500/10 px-4 py-3 text-sm text-success-500">
              已创建并发布配置 {commitResult.configuration_id}（修订 #
              {commitResult.revision_number}），包含 {commitResult.field_count} 个字段。
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
