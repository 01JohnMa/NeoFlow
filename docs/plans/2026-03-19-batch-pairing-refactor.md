# 批处理配对模式重构计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把"处理模式"从模板配置（`process_mode`）移到用户操作层面——用户在批处理页面决定文件是单独处理还是配对合并，模板只负责字段定义和飞书配置，不再区分 single/merge。

**Architecture:**
- `BatchItem` 去掉 `type` 字段，改为统一结构：有 `paired_document_id` 就走 merge，没有就走 single
- `template_merge_rules` 表废弃（配对关系由用户在页面指定，不需要预配置）
- `document_templates.process_mode` 字段保留但不再约束批处理行为（兼容历史）
- 前端批处理页面：每行文件可选择"单独处理"或"配对"，配对时选第二个文件和合并飞书模板

**Tech Stack:** Python FastAPI, Pydantic, React/TypeScript, Supabase

---

## 当前 vs 新设计对比

| 维度 | 当前 | 新设计 |
|------|------|------|
| 积分球模板 | `process_mode=merge`，只能配对 | 普通模板，可单独也可配对 |
| 批处理 item | `type: "single"\|"merge"` 两种结构 | 统一结构，`paired_with` 可选 |
| 配对规则 | 存在 `template_merge_rules` 表 | 用户在页面指定，无需预配置 |
| 飞书推送 | 合并模板的飞书配置 | 配对时指定用哪个模板的飞书配置 |

---

## Task 1：更新 `BatchItem` schema 和批处理接口

**Files:**
- Modify: `api/routes/documents/batch.py`

**Step 1: 重写 `BatchItem`**

```python
class BatchItem(BaseModel):
    document_id: str                          # 主文档 ID
    template_id: str                          # 主文档模板 ID
    # 配对字段（可选，有则走 merge 逻辑）
    paired_document_id: Optional[str] = None  # 配对文档 ID
    paired_template_id: Optional[str] = None  # 配对文档模板 ID
    feishu_template_id: Optional[str] = None  # 合并推送用的飞书模板 ID（默认用 template_id）
```

**Step 2: 更新校验逻辑**

```python
@validator("paired_document_id")
def validate_pair(cls, v, values):
    if v and not values.get("paired_template_id"):
        raise ValueError("配对模式需要同时提供 paired_template_id")
    return v
```

**Step 3: 更新批处理主函数**

```python
async def _process_batch_item(job_id, idx, item, user):
    if item.paired_document_id:
        await _process_merge_item(job_id, idx, item, user)
    else:
        await _process_single_item(job_id, idx, item, user)
```

**Step 4: 重写 `_process_single_item` 适配新 schema**

原来用 `item.document_id`，新 schema 一致，只需确认字段名对齐。

**Step 5: 重写 `_process_merge_item` 适配新 schema**

```python
async def _process_merge_item(job_id, idx, item, user):
    doc_a = await supabase_service.get_document(item.document_id)
    doc_b = await supabase_service.get_document(item.paired_document_id)
    template_a = await template_service.get_template_with_details(item.template_id)
    template_b = await template_service.get_template_with_details(item.paired_template_id)
    # 飞书推送模板：优先用 feishu_template_id，fallback 到 template_id
    feishu_template_id = item.feishu_template_id or item.template_id
    feishu_template = await template_service.get_template_with_details(feishu_template_id)
    # ... 后续 OCR + 存储 + 推送逻辑不变
```

**Step 6: Commit**

```bash
git add api/routes/documents/batch.py
git commit -m "refactor: BatchItem unified schema, pairing driven by user not template process_mode"
```

---

## Task 2：更新 `process.py` 的 `_run_merge_job`

**Files:**
- Modify: `api/routes/documents/process.py`

`_run_merge_job` 目前依赖 `template_merge_rules` 查子模板。新设计下，子模板信息直接从调用方传入（`sub_template_a_id = item.template_id`，`sub_template_b_id = item.paired_template_id`），不再查 `merge_rules`。

**Step 1: 修改函数签名，增加 `sub_template_a_id` / `sub_template_b_id` 参数**

```python
async def _run_merge_job(
    job_id: str,
    files: list,
    source_doc_ids: list,
    template: dict,           # 飞书推送模板
    sub_template_a_id: str,   # 新增
    sub_template_b_id: str,   # 新增
    user: CurrentUser,
):
```

**Step 2: 删除 `get_merge_template_info` 调用**

原来：
```python
merge_template_info = await template_service.get_merge_template_info(template_uuid)
sub_template_a = merge_template_info.get("sub_template_a")
sub_template_b = merge_template_info.get("sub_template_b")
```

新：
```python
sub_template_a = await template_service.get_template_with_details(sub_template_a_id)
sub_template_b = await template_service.get_template_with_details(sub_template_b_id)
```

**Step 3: Commit**

```bash
git add api/routes/documents/process.py
git commit -m "refactor: _run_merge_job accepts sub_template ids directly, removes merge_rules dependency"
```

---

## Task 3：`workflow.py` 的 `process_merge` 去掉 `doc_type` 依赖

**Files:**
- Read: `agents/workflow.py` 的 `process_merge` 函数
- Modify if needed

当前 `process_merge` 用 `doc_type_a/b`（如 `"积分球"`/`"光分布"`）来区分两份文档。新设计下直接用 `sub_template_a/b` 的字段定义来驱动提取，不依赖字符串类型标签。

**Step 1: 确认 `process_merge` 的 `doc_type` 用途**

```bash
grep -n "doc_type" agents/workflow.py
```

**Step 2: 如果 `doc_type` 只用于日志和字段过滤，改为从模板 `code` 或 `name` 取值**

```python
# 修改前
doc_type_a = file_a.get("doc_type", "文档A")
# 修改后
doc_type_a = sub_template_a.get("code") or sub_template_a.get("name", "文档A")
```

**Step 3: Commit**

```bash
git add agents/workflow.py
git commit -m "fix: process_merge uses template code instead of doc_type string"
```

---

## Task 4：前端 `BatchMergePairing` 组件重构

**Files:**
- Modify: `web/src/components/BatchMergePairing.tsx`
- Modify: `web/src/pages/Upload.tsx`（或批处理页面）

**Step 1: 新的交互设计**

每个上传文件行有两种状态：
- **单独处理**（默认）：选择模板 → 提交
- **配对处理**：选择本文件模板 + 选择配对文件 + 选择配对文件模板 + 选择飞书推送模板（可选，默认用本文件模板）

```tsx
interface BatchItemConfig {
  documentId: string
  templateId: string
  // 配对（可选）
  pairedDocumentId?: string
  pairedTemplateId?: string
  feishuTemplateId?: string  // 默认 = templateId
}
```

**Step 2: 更新提交逻辑**

```ts
// 构造 BatchItem（新 schema）
const items = configs.map(cfg => ({
  document_id: cfg.documentId,
  template_id: cfg.templateId,
  paired_document_id: cfg.pairedDocumentId,
  paired_template_id: cfg.pairedTemplateId,
  feishu_template_id: cfg.feishuTemplateId,
}))
await api.post('/documents/batch-process', { items })
```

**Step 3: 模板选择器不再按 `process_mode` 过滤**

原来前端可能只显示 `process_mode=single` 的模板给 single 行，`process_mode=merge` 的给 merge 行。新设计下所有 `is_active=true` 的模板都可选。

**Step 4: Commit**

```bash
git add web/src/components/BatchMergePairing.tsx web/src/pages/Upload.tsx
git commit -m "feat: batch pairing driven by user selection, all templates available"
```

---

## Task 5：数据库清理（可选，不影响功能）

**Files:**
- Create: `supabase/migrations/009_cleanup_process_mode.sql`

`template_merge_rules` 表和 `document_templates.process_mode` 字段不再被代码使用，可以保留（兼容历史）或清理。

建议：**保留字段，不删除**，只在注释里标记为 deprecated。如果未来确认不需要再做迁移。

---

## Task 6：更新 `002_init_data.sql` 中积分球模板的 `process_mode`

**Files:**
- Modify: `supabase/migrations/002_init_data.sql`

把积分球模板的 `process_mode` 改为 `single`（或保持 `merge` 但代码不再依赖它）。

```sql
UPDATE document_templates
    SET process_mode = 'single'
    WHERE code = 'integrating_sphere';
```

这样前端模板列表不再需要特殊处理，所有模板都可以出现在 single 选择器里。

**Step 2: 在容器内执行**

```bash
docker exec supabase-db psql -U postgres -d postgres -c \
  "UPDATE document_templates SET process_mode='single' WHERE code='integrating_sphere';"
```

**Step 3: Commit**

```bash
git add supabase/migrations/002_init_data.sql
git commit -m "fix: integrating_sphere process_mode=single, pairing handled by UI"
```

---

## 验证清单

- [ ] 积分球单独批处理：提取 14 个字段，写入 `integrating_sphere_reports`，推飞书
- [ ] 光分布单独批处理：提取 8 个字段，写入 `light_distribution_reports`，推飞书
- [ ] 积分球 + 光分布配对批处理：各自存各自表，配对关系记录，双方审核后合并推飞书
- [ ] 其他部门（质量管理中心）批处理不受影响
- [ ] 前端模板选择器显示所有 `is_active=true` 的模板
