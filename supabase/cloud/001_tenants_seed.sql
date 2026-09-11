-- ============================================================
-- 云版租户 seed（Supabase Cloud 专用）
-- ============================================================
-- 只保留 002_init_data.sql 的租户初始化，不导入旧模板/字段/示例
-- （新配置通过管理后台或 AI 向导创建）。
-- 执行顺序：在 001_multi_tenant.sql 之后执行。
-- ============================================================

-- 质量管理中心
INSERT INTO tenants (id, name, code, description, is_active) VALUES
    ('a0000000-0000-0000-0000-000000000001', '质量管理中心', 'quality', '负责产品质量检验报告处理', TRUE)
ON CONFLICT (code) DO NOTHING;

-- 照明事业部
INSERT INTO tenants (id, name, code, description, is_active) VALUES
    ('a0000000-0000-0000-0000-000000000002', '照明事业部', 'lighting', '负责照明产品测试报告处理', TRUE)
ON CONFLICT (code) DO NOTHING;

SELECT 'cloud/001_tenants_seed.sql: 租户初始化完成' AS message;
