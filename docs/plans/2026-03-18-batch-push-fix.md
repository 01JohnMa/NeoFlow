# Batch Push Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复批处理中 single 和 merge 模式的推送逻辑，使推送行为统一为"识别到哪些字段就推送哪些字段"，不再依赖 `document_type → TABLE_MAP` 的硬编码映射。

**Architecture:** 当前问题根源有两个：(1) `save_extraction_result` 依赖 `TABLE_MAP` 查表名，`light_distribution` 未注册导致 single 模式无法入库；(2) merge 模式在 `_process_merge_item` 中用 `template_name`（中文名）作为 `document_type` 传给 `save_extraction_result`，而 `TABLE_MAP` 里也没有这个中文名的映射。修复方向：让 `save_extraction_result` 接受显式 `table_name` 参数，或在调用侧直接传入正确的表名；同时补全 `DOC_TYPE_TABLE_MAP` 中缺失的 `light_distribution` 映射。

**Tech Stack:** Python, FastAPI, Supabase, `constants/document_types.py`, `services/supabase_service.py`, `api/routes/documents/batch.py`

---

## 问题全景

### 问题 1：`light_distribution` 未注册（single 模式）

**调用链：**
```
batch.py _process_single_item
  → handle_processing_success(result)
    → save_extraction_result(document_id, document_type="light_distribution", ...)
      → TABLE_MAP.get("light_distribution")  # → None
        → WARNING: 未知文档类型，直接 return None（数据丢失）
```

**根因：** `constants/document_types.py` 的 `DOC_TYPE_TABLE_MAP` 缺少 `light_distribution` 键。

---

### 问题 2：merge 模式用中文模板名作 document_type

**调用链：**
```
batch.py _process_merge_item
  → save_extraction_result(document_id, document_type=template_name, ...)
    # template_name = "照明综合报告" 或 "光分布测试" 等中文名
    → TABLE_MAP.get("照明综合报告")  # 可能命中，也可能不命中
```

`_process_merge_item` 第 245 行：
```python
"document_type": template_name,   # ← 用的是中文名
```
第 256-260 行：
```python
await supabase_service.save_extraction_result(
    document_id=doc_id,
    document_type=template_name,   # ← 同样是中文名
    extraction_data=sample_data,
)
```

`TABLE_MAP` 里有 `"照明综合报告"` 但没有 `"光分布测试"`，所以光分布单独上传时 merge 路径也会失败。

---

### 问题 3：设计意图 vs 实现

用户期望：**识别到哪些字段就推送哪些字段**，不应该因为 `document_type` 字符串没注册就静默丢弃数据。

正确做法：
- `save_extraction_result` 应该能通过模板的 `code` 或显式传入的 `table_name` 找到目标表
- 或者：在调用侧直接用 `template.get("code")` 而不是 `template_name`

---

## Task 1：补全 `DOC_TYPE_TABLE_MAP`（最小修复，解决 single 模式）

**Files:**
- Modify: `constants/document_types.py`

**Step 1: 确认 `light_distribution` 应映射到哪张表**

查看数据库中是否有 `light_distribution_reports` 表，还是复用 `lighting_reports`。
根据业务逻辑（光分布是照明综合报告的子文档），映射到 `lighting_reports`。

**Step 2: 添加映射**

在 `DOC_TYPE_TABLE_MAP` 的照明区块添加：

```python
# 光分布测试（照明综合报告的子文档类型）
"light_distribution": DocumentTypeTable.LIGHTING_REPORT,
"光分布测试": DocumentTypeTable.LIGHTING_REPORT,
```

**Step 3: 验证**

重新触发 single 模式批处理，确认日志不再出现 `WARNING: 未知文档类型: light_distribution`。

**Step 4: Commit**

```bash
git add constants/document_types.py
git commit -m "fix: add light_distribution mapping to DOC_TYPE_TABLE_MAP"
```

---

## Task 2：修复 merge 模式的 `document_type` 传值

**Files:**
- Modify: `api/routes/documents/batch.py:240-260`

**问题代码（batch.py 第 240-260 行）：**

```python
doc_data = {
    ...
    "document_type": template_name,   # ← 中文名，不稳定
    ...
}
await supabase_service.save_extraction_result(
    document_id=doc_id,
    document_type=template_name,       # ← 同样是中文名
    extraction_data=sample_data,
)
```

**修复：** 用 `template.get("code", template_name)` 替代 `template_name`，优先使用模板的 `code` 字段（英文标识符，与 `TABLE_MAP` 的键一致）。

**Step 1: 在 `_process_merge_item` 中提取 template code**

在第 193 行附近，`template_uuid = template.get("id")` 之后添加：

```python
template_code = template.get("code") or template_name
```

**Step 2: 替换 `document_type` 的赋值**

```python
# 修改前
"document_type": template_name,

# 修改后
"document_type": template_code,
```

**Step 3: 替换 `save_extraction_result` 的 `document_type` 参数**

```python
# 修改前
await supabase_service.save_extraction_result(
    document_id=doc_id,
    document_type=template_name,
    extraction_data=sample_data,
)

# 修改后
await supabase_service.save_extraction_result(
    document_id=doc_id,
    document_type=template_code,
    extraction_data=sample_data,
)
```

**Step 4: Commit**

```bash
git add api/routes/documents/batch.py
git commit -m "fix: use template code instead of name for merge document_type"
```

---

## Task 3：`save_extraction_result` 增加兜底逻辑（防御性修复）

**Files:**
- Modify: `services/supabase_service.py:450-461`

当前实现在找不到 `table_name` 时直接 `return None`，数据静默丢失。

**修复：** 增加一个兜底表（`lighting_reports` 或通用的 `documents_extraction`），或者至少把 WARNING 升级为 ERROR 并记录完整的 `extraction_data` 摘要，方便排查。

**Step 1: 升级日志级别并记录数据摘要**

```python
async def save_extraction_result(
    self,
    document_id: str,
    document_type: str,
    extraction_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    table_name = self.TABLE_MAP.get(document_type)
    if not table_name:
        logger.error(
            f"未知文档类型: {document_type}，无法保存提取结果。"
            f"document_id={document_id}, fields={list(extraction_data.keys())}"
        )
        return None
    return await self._save_to_table(table_name, document_id, extraction_data)
```

**Step 2: Commit**

```bash
git add services/supabase_service.py
git commit -m "fix: upgrade unknown doc type log to ERROR with field summary"
```

---

## Task 4：验证完整批处理流程

**Step 1: 触发 single 模式（光分布单文件）**

上传一份光分布 PDF，选择 `光分布测试` 模板，提交批处理。

预期日志：
- 不再出现 `WARNING: 未知文档类型: light_distribution`
- 出现 `INFO: 提取结果已保存: <document_id>`

**Step 2: 触发 merge 模式（积分球 + 光分布配对）**

上传积分球 + 光分布各一份，提交 merge 批处理。

预期：两份文档均成功入库，飞书推送成功。

**Step 3: 检查 `lighting_reports` 表**

确认 single 和 merge 两种路径的数据都写入了 `lighting_reports` 表。

---

## 变更文件汇总

| 文件 | 变更内容 |
|------|---------|
| `constants/document_types.py` | 添加 `light_distribution` / `光分布测试` 映射 |
| `api/routes/documents/batch.py` | merge 路径改用 `template.code` 而非 `template_name` |
| `services/supabase_service.py` | 未知类型日志升级为 ERROR，记录字段摘要 |
