-- ============================================================
-- 数据库与 migrations 一致性验证脚本
-- 用法: docker exec -i supabase-db psql -U postgres -d postgres -f - < scripts/verify_db_migrations.sql
-- ============================================================

\echo '============================================'
\echo '1. 检查 public schema 表是否存在'
\echo '============================================'
SELECT tablename as "表名" FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

\echo ''
\echo '============================================'
\echo '2. 租户数据 (tenants) - 期望: 2条'
\echo '============================================'
SELECT id, name, code, is_active FROM tenants ORDER BY code;
SELECT '期望: quality, lighting 两个租户' as note;

\echo ''
\echo '============================================'
\echo '3. 文档模板 (document_templates) - 期望: 5条'
\echo '============================================'
SELECT dt.id, t.code as tenant_code, dt.name, dt.code, dt.process_mode, dt.required_doc_count, dt.is_active, dt.feishu_bitable_token IS NOT NULL as has_feishu
FROM document_templates dt
JOIN tenants t ON t.id = dt.tenant_id
ORDER BY t.code, dt.sort_order;

\echo ''
\echo '============================================'
\echo '4. 模板字段数量 - 期望: 检测报告18, 快递单6, 抽样单12, 积分球20, 光分布6'
\echo '============================================'
SELECT dt.code as template_code, COUNT(tf.id) as field_count
FROM document_templates dt
LEFT JOIN template_fields tf ON tf.template_id = dt.id
GROUP BY dt.id, dt.code
ORDER BY dt.code;

\echo ''
\echo '============================================'
\echo '5. 合并规则 (template_merge_rules) - 期望: 1条 (积分球)'
\echo '============================================'
SELECT tmr.template_id, dt.code as main_template, tmr.doc_type_a, tmr.doc_type_b
FROM template_merge_rules tmr
JOIN document_templates dt ON dt.id = tmr.template_id;

\echo ''
\echo '============================================'
\echo '6. 模板示例 (template_examples) - 期望: 5条'
\echo '============================================'
SELECT dt.code, COUNT(te.id) as example_count
FROM document_templates dt
LEFT JOIN template_examples te ON te.template_id = dt.id
GROUP BY dt.id, dt.code
ORDER BY dt.code;

\echo ''
\echo '============================================'
\echo '7. 检测报告字段 review_enforced 和 extraction_hint'
\echo '============================================'
SELECT field_key, review_enforced, review_allowed_values, extraction_hint
FROM template_fields 
WHERE template_id = 'b0000000-0000-0000-0000-000000000001' 
  AND field_key = 'inspection_conclusion';

\echo ''
\echo '============================================'
\echo '8. 飞书推送配置'
\echo '============================================'
SELECT dt.code, dt.feishu_bitable_token, dt.feishu_table_id
FROM document_templates dt
WHERE dt.feishu_bitable_token IS NOT NULL
ORDER BY dt.code;

\echo ''
\echo '============================================'
\echo '9. documents 表 tenant_id/template_id 列'
\echo '============================================'
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'public' AND table_name = 'documents' 
  AND column_name IN ('tenant_id', 'template_id');

\echo ''
\echo '============================================'
\echo '10. 唯一约束检查 (document_templates UNIQUE tenant_id, code)'
\echo '============================================'
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'document_templates'::regclass 
  AND contype = 'u';
