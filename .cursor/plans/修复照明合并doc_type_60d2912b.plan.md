---
name: 修复照明合并doc_type
overview: 修复合并提取为空问题：前端发送符合 merge_rule 的 doc_type（积分球/光分布），界面继续显示“积分球报告/光分布报告”。模板标识固定使用 lighting_combined。
todos:
  - id: update-doc-type-mapping
    content: 调整 LIGHTING_DOC_TYPES 显示/发送分离，并更新合并上传的 doc_type
    status: pending
isProject: false
---

# 修复照明合并 doc_type

## 根因

合并流程在 `agents/workflow.py` 通过 `doc_type` 精确匹配 `template_merge_rules.doc_type_a/doc_type_b`。数据库配置为“积分球/光分布”，但前端发送“积分球报告/光分布报告”，导致 `result_a/result_b` 为 None，最终合并结果为空。

## 方案

在前端使用“显示名/发送值”分离：

- 显示：积分球报告、光分布报告
- 发送：积分球、光分布（用于匹配 merge_rule）

模板标识保持固定 `lighting_combined`（仅用于 process-merge）。

## 修改点

1. **前端常量调整**

在 [web/src/pages/Upload.tsx](web/src/pages/Upload.tsx) 将 `LIGHTING_DOC_TYPES` 改为包含 `label` 与 `value` 的数组：

```tsx
const LIGHTING_DOC_TYPES = [
  { label: '积分球报告', value: '积分球' },
  { label: '光分布报告', value: '光分布' },
]
```

1. **初始化 mergeFiles**

初始化时用 `label` 作为界面展示、`value` 作为 `docType` 存储：

- `docType` 存 `value`（发送给后端）
- 新增 `displayName` 或直接在渲染时从常量映射

1. **渲染与上传**

- 上传区域、说明文字使用 `label`
- `handleMergeUpload` 仍发送 `doc_type: item.docType`（现在是“积分球/光分布”）

## 影响评估

- 仅影响照明合并上传的 doc_type 传参
- 质量管理中心上传流程不变

## 文件

- [web/src/pages/Upload.tsx](web/src/pages/Upload.tsx)

