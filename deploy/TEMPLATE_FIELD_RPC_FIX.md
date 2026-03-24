# 模板配置「新增字段」422 / 物理列与 template_fields 不一致 — 说明与回归

## 根因（简述）

`supabase-py` 调用返回 JSONB 的 RPC 时，成功结果偶发以「异常体」形式出现；`schema_sync_service._execute_rpc_jsonb` 会从 `execute()` 异常中解析含 `success` 的 JSONB，避免误判为失败。

## 部署后回归验证

1. **全新字段**：在模板配置页新增 `field_key`（如 `regression_test_001`），应返回 **201**，且：
   - `template_fields` 存在对应行；
   - `information_schema.columns` 中结果表存在该列。
2. **幂等**：若物理列已存在，再次新增同 `field_key`，应 **201**（或至少不再出现 `success: True` 仍 422）。
3. **非法键名**：如大写开头的 `BadKey`，应 **422**，且 `detail` 为数据库函数返回的校验文案。
4. **日志**：`neoflow-api` 中不应再出现 `遇到异常: {'success': True, ...}` 类错误。

运行单元测试（需已安装项目依赖 `pip install -r requirements.txt`）：

```bash
python -m pytest tests/test_schema_sync_service.py -v
```

## 线上脏数据补救

若曾出现「结果表已有列、`template_fields` 无记录」，配置页不会显示该字段。在确认 `field_key` 与 `template_id` 后，可补插 `template_fields`（注意 `UNIQUE(template_id, field_key)`）。

示例（请替换为实际 `template_id` / 文案 / 排序）：

```sql
select id from template_fields
where template_id = 'YOUR_TEMPLATE_UUID'
  and field_key = 'your_field_key';

-- 无行时再执行 insert，见仓库内迁移或管理端 SQL 工具按表结构补全列。
```

部署本修复后，也可在页面再次「新增」同名字段：DDL 幂等成功后应能写入 `template_fields`。

## 可选：刷新 PostgREST schema

```sql
NOTIFY pgrst, 'reload schema';
```

---

## `services` 包惰性加载

`services/__init__.py` 改为惰性导出 `ocr_service` / `feishu_service` / `supabase_service`，避免仅运行与 OCR 无关的测试时强制导入 `paddleocr`。
