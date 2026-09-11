-- ============================================================
-- MIGRATION 022: Result 存储 + Job 固定 Configuration Revision
-- ============================================================
-- 引入统一、append-only 的 results 表：
--   * 每条抽取样品一行，data/field_meta 记录字段值与逐字段 provenance
--   * review_state 供后续审核流程流转
--   * tenant_id 显式隔离；job_id / document_id / config_revision_id 可追溯
--
-- processing_jobs 增加：
--   * configuration_revision_id：Job 固定创建时选定的不可变 Revision（历史 job 为 NULL）
--   * tenant_id：Job 归属租户，供 API 做租户隔离
--
-- 本迁移不删除、不重命名旧模板/业务表；旧代码路径保持可用，
-- 读取侧迁移见后续票。
--
-- 幂等性：本文件可重复执行（IF NOT EXISTS / NOT EXISTS / CREATE OR REPLACE）。
-- ============================================================

-- ############################################################
-- PART 1: processing_jobs 增加 Revision 固定与租户归属
-- ############################################################

ALTER TABLE processing_jobs
    ADD COLUMN IF NOT EXISTS configuration_revision_id UUID,
    ADD COLUMN IF NOT EXISTS tenant_id UUID;

CREATE INDEX IF NOT EXISTS idx_processing_jobs_configuration_revision_id
    ON processing_jobs(configuration_revision_id);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_tenant_id
    ON processing_jobs(tenant_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'processing_jobs_configuration_revision_id_fkey'
    ) THEN
        ALTER TABLE processing_jobs
            ADD CONSTRAINT processing_jobs_configuration_revision_id_fkey
            FOREIGN KEY (configuration_revision_id)
            REFERENCES configuration_revisions(id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'processing_jobs_tenant_id_fkey'
    ) THEN
        ALTER TABLE processing_jobs
            ADD CONSTRAINT processing_jobs_tenant_id_fkey
            FOREIGN KEY (tenant_id)
            REFERENCES tenants(id)
            ON DELETE CASCADE;
    END IF;
END $$;

-- ############################################################
-- PART 2: results（append-only 抽取结果）
-- ############################################################

CREATE TABLE IF NOT EXISTS results (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    job_id              UUID REFERENCES processing_jobs(job_id) ON DELETE SET NULL,
    document_id         UUID REFERENCES documents(id) ON DELETE SET NULL,
    config_revision_id  UUID REFERENCES configuration_revisions(id) ON DELETE SET NULL,
    sample_key          TEXT NOT NULL DEFAULT 'default',
    data                JSONB NOT NULL DEFAULT '{}'::jsonb,
    field_meta          JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_state        VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (review_state IN ('pending', 'approved', 'rejected')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_results_tenant_created_at
    ON results(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_results_job_id
    ON results(job_id);
CREATE INDEX IF NOT EXISTS idx_results_document_id
    ON results(document_id);
CREATE INDEX IF NOT EXISTS idx_results_config_revision_id
    ON results(config_revision_id);

DROP TRIGGER IF EXISTS update_results_updated_at ON results;
CREATE TRIGGER update_results_updated_at
    BEFORE UPDATE ON results
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ############################################################
-- PART 3: RLS 与权限（成员可读本租户，管理员可管理；跨租户不可见）
-- ############################################################

ALTER TABLE results ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON results FROM anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON results TO authenticated;
GRANT ALL ON results TO service_role;

DROP POLICY IF EXISTS "Tenant members can view results" ON results;
CREATE POLICY "Tenant members can view results" ON results
    FOR SELECT USING (
        tenant_id = get_current_user_tenant_id()
        OR get_current_user_role() = 'super_admin'
    );

DROP POLICY IF EXISTS "Tenant admins can manage results" ON results;
CREATE POLICY "Tenant admins can manage results" ON results
    FOR ALL USING (
        get_current_user_role() = 'super_admin'
        OR (
            tenant_id = get_current_user_tenant_id()
            AND get_current_user_role() IN ('tenant_admin', 'super_admin')
        )
    )
    WITH CHECK (
        get_current_user_role() = 'super_admin'
        OR (
            tenant_id = get_current_user_tenant_id()
            AND get_current_user_role() IN ('tenant_admin', 'super_admin')
        )
    );

DROP POLICY IF EXISTS "Service role full access to results" ON results;
CREATE POLICY "Service role full access to results" ON results
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

SELECT pg_notify('pgrst', 'reload schema');
SELECT '022: results 表与 processing_jobs.configuration_revision_id 就绪' AS message;
