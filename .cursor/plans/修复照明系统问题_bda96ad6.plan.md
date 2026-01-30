---
name: 解耦照明与质量运营上传逻辑
overview: 重构 Upload.tsx，解耦照明系统和质量运营部的上传逻辑。照明系统始终显示两文件合并上传，质量运营使用单文件自动识别，两者逻辑独立互不影响。
todos:
  - id: refactor-upload-decouple
    content: 重构 Upload.tsx：根据 tenantCode 直接决定上传模式，移除复杂的级联判断
    status: completed
  - id: lighting-fixed-merge
    content: 照明系统固定显示两文件上传界面（积分球 + 光分布），不依赖 templates/mergeRules 查询
    status: completed
  - id: quality-auto-mode
    content: 质量运营保持单文件自动识别模式
    status: completed
  - id: error-handling
    content: 添加 tenantCode 为空时的错误提示
    status: completed
---

# 解耦照明系统与质量运营上传逻辑

## 问题分析

当前 Upload.tsx 的逻辑耦合过强：

```
tenantCode → isQualityTenant → 是否显示模板选择
     ↓
templates → selectedTemplate → isMergeMode → 显示哪种上传界面
     ↓
mergeRules → mergeFiles → merge 模式的文档类型
```

**问题**：当任何一环数据获取失败，整个界面就会错乱。照明系统和质量运营的逻辑混在一起，互相影响。

## 解耦方案

### 核心思路：根据 tenantCode 直接决定上传模式

```
tenantCode === 'lighting' → 显示固定的两文件上传界面
tenantCode === 'quality'  → 显示单文件自动识别界面
tenantCode 为空          → 显示错误提示
```

### 修改 Upload.tsx

**1. 定义上传模式常量**

```tsx
// 照明系统固定的文档类型配置
const LIGHTING_DOC_TYPES = ['积分球报告', '光分布报告']

// 上传模式枚举
type UploadMode = 'lighting_merge' | 'quality_auto' | 'unknown'
```

**2. 简化模式判断**

```tsx
// 直接根据 tenantCode 决定模式，不依赖 templates 查询结果
const uploadMode: UploadMode = useMemo(() => {
  if (tenantCode === 'lighting') return 'lighting_merge'
  if (tenantCode === 'quality') return 'quality_auto'
  return 'unknown'
}, [tenantCode])
```

**3. 照明系统：固定两文件上传**

照明系统不再依赖 `mergeRules` 查询，直接使用固定配置：

- 文档1：积分球报告
- 文档2：光分布报告

**4. 质量运营：保持现有逻辑**

单文件上传 + 后端自动识别文档类型

**5. 未知模式：显示错误提示**

```tsx
{uploadMode === 'unknown' && (
  <Card className="border-warning-500">
    <CardContent>
      <p>请先在设置中选择所属部门</p>
    </CardContent>
  </Card>
)}
```

## 修改前后对比

### 修改前（高耦合）

```tsx
const isQualityTenant = tenantCode === 'quality'
const selectedTemplate = templates.find(t => t.id === selectedTemplateId)
const isMergeMode = selectedTemplate?.process_mode === 'merge'

// 依赖 templates 加载
useEffect(() => {
  if (isQualityTenant) { ... }
  if (templates.length > 0 && !selectedTemplateId) { ... }
}, [templates, selectedTemplateId, isQualityTenant])

// 依赖 mergeRules 加载
useEffect(() => {
  if (selectedTemplateId && isMergeMode && mergeFiles.length === 0) {
    const rule = mergeRules?.find(r => r.template_id === selectedTemplateId)
    // ...
  }
}, [selectedTemplateId, isMergeMode, mergeRules, mergeFiles.length])
```

### 修改后（解耦）

```tsx
const uploadMode = useMemo(() => {
  if (tenantCode === 'lighting') return 'lighting_merge'
  if (tenantCode === 'quality') return 'quality_auto'
  return 'unknown'
}, [tenantCode])

// 照明系统直接初始化固定的两文件列表
useEffect(() => {
  if (uploadMode === 'lighting_merge' && mergeFiles.length === 0) {
    setMergeFiles(LIGHTING_DOC_TYPES.map((docType, index) => ({
      id: `merge-${index}`,
      file: null,
      docType,
      preview: null,
    })))
  }
}, [uploadMode])
```

## 文件修改清单

- [web/src/pages/Upload.tsx](web/src/pages/Upload.tsx)
  - 添加 `UploadMode` 类型和 `LIGHTING_DOC_TYPES` 常量
  - 用 `uploadMode` 替代 `isQualityTenant` 和 `isMergeMode` 的复杂判断
  - 照明系统使用固定配置，不依赖 API 查询结果
  - 添加 `unknown` 模式的错误提示

## 优势

1. **独立性**：照明和质量运营的逻辑完全分离
2. **稳定性**：照明系统不依赖 templates/mergeRules 查询，即使查询失败也能正常显示
3. **可维护性**：新增租户只需添加一个 case，不影响现有逻辑
4. **可读性**：一目了然的模式判断，替代复杂的条件嵌套