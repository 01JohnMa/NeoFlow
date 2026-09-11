-- ============================================================
-- MIGRATION 020: 安全加固 - 补齐 RLS/权限，收紧缺少 WITH CHECK 的策略
-- ============================================================
-- 背景（架构审计发现）：
--   * 012 创建的 processing_jobs / feishu_push_records 未启用 RLS，
--     而 000_init.sql 的 ALTER DEFAULT PRIVILEGES 把 ALL 授予了
--     anon/authenticated，PostgREST 可直接读写这两张表。
--   * profiles 的 UPDATE 策略只有 USING；PostgreSQL 对 ALL/UPDATE 策略
--     在缺少 WITH CHECK 时会复用 USING，这里显式补上，并禁止普通用户
--     改写 role / tenant_id，避免提权。
--
-- 安全姿态：
--   * API / worker 一律使用 service_role（BYPASSRLS），不受影响。
--   * 前端不直接经 PostgREST 访问这两张表，因此默认拒绝，不做放行。
-- ============================================================

-- 1. processing_jobs：启用 RLS，收回 anon/authenticated 的直接表权限
ALTER TABLE processing_jobs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON processing_jobs FROM anon, authenticated;
GRANT ALL ON processing_jobs TO service_role;

DROP POLICY IF EXISTS "Service role can manage all processing_jobs" ON processing_jobs;
CREATE POLICY "Service role can manage all processing_jobs" ON processing_jobs
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- 2. feishu_push_records：同上
ALTER TABLE feishu_push_records ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON feishu_push_records FROM anon, authenticated;
GRANT ALL ON feishu_push_records TO service_role;

DROP POLICY IF EXISTS "Service role can manage all feishu_push_records" ON feishu_push_records;
CREATE POLICY "Service role can manage all feishu_push_records" ON feishu_push_records
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- 3. worker 认领函数只允许 service_role 调用（RLS 开启后匿名调用本身已查不到行）
REVOKE EXECUTE ON FUNCTION claim_next_processing_job(TEXT, INT) FROM anon, authenticated;

-- 4. profiles：显式 WITH CHECK，且 role / tenant_id 不允许被本人改写
DROP POLICY IF EXISTS "Users can update own profile" ON profiles;
CREATE POLICY "Users can update own profile" ON profiles
    FOR UPDATE
    USING (id = auth.uid())
    WITH CHECK (
        id = auth.uid()
        AND role = get_current_user_role()
        AND tenant_id IS NOT DISTINCT FROM get_current_user_tenant_id()
    );

SELECT pg_notify('pgrst', 'reload schema');
SELECT '020: RLS 权限补齐完成（processing_jobs / feishu_push_records / profiles）' AS message;
