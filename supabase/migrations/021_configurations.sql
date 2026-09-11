-- ============================================================
-- MIGRATION 021: 领域底座 - Project / Configuration / Configuration Revision
-- ============================================================
-- 引入 Tenant -> Project -> Configuration(+不可变 Revision) 领域模型：
--   * projects               每个租户一个默认项目（最小实现）
--   * configurations         项目所有，draft -> published -> archived
--   * configuration_revisions 发布快照，只增不改（触发器拒绝 UPDATE）
--   * 现有 document_templates（字段、示例、prompt、提取模式、Excel 元数据）
--     幂等迁移为已发布 Configuration + Revision
--
-- 本迁移不删除、不重命名旧模板表，旧代码路径（AI 向导、文档处理、管理 UI）
-- 保持可用；读取侧迁移见后续票。
--
-- 幂等性：本文件可重复执行（IF NOT EXISTS / NOT EXISTS / CREATE OR REPLACE）。
-- ============================================================

-- ############################################################
-- PART 1: projects
-- ############################################################

CREATE TABLE IF NOT EXISTS projects (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 每个租户至多一个默认项目
CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_tenant_default
    ON projects(tenant_id) WHERE is_default;

CREATE INDEX IF NOT EXISTS idx_projects_tenant_id ON projects(tenant_id);

DROP TRIGGER IF EXISTS update_projects_updated_at ON projects;
CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ############################################################
-- PART 2: configurations
-- ############################################################

CREATE TABLE IF NOT EXISTS configurations (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name                VARCHAR(100) NOT NULL,
    code                VARCHAR(50),
    description         TEXT,
    type                VARCHAR(20) NOT NULL DEFAULT 'extract'
        CHECK (type IN ('parse', 'extract', 'classify', 'split', 'composite')),
    status              VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'archived')),
    -- 可编辑草稿；发布时由 draft_definition 生成新的不可变 Revision
    draft_definition    JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- 指向最近一次发布产生的 Revision（草稿配置为 NULL）
    current_revision_id UUID,
    -- 数据迁移溯源：来自哪个 document_templates 记录（不设外键，便于后续删除旧表）
    legacy_template_id  UUID,
    created_by          UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, code),
    UNIQUE (legacy_template_id)
);

CREATE INDEX IF NOT EXISTS idx_configurations_tenant_id ON configurations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_configurations_project_id ON configurations(project_id);
CREATE INDEX IF NOT EXISTS idx_configurations_status ON configurations(status);
CREATE INDEX IF NOT EXISTS idx_configurations_type ON configurations(type);

DROP TRIGGER IF EXISTS update_configurations_updated_at ON configurations;
CREATE TRIGGER update_configurations_updated_at
    BEFORE UPDATE ON configurations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ############################################################
-- PART 3: configuration_revisions（不可变发布快照）
-- ############################################################

CREATE TABLE IF NOT EXISTS configuration_revisions (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    configuration_id UUID NOT NULL REFERENCES configurations(id) ON DELETE CASCADE,
    revision_number  INT NOT NULL,
    definition       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by       UUID,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at     TIMESTAMPTZ,
    UNIQUE (configuration_id, revision_number)
);

CREATE INDEX IF NOT EXISTS idx_configuration_revisions_configuration_id
    ON configuration_revisions(configuration_id);

-- 已生成的 Revision 不允许再 UPDATE（内容快照不可变）
CREATE OR REPLACE FUNCTION prevent_configuration_revision_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'configuration_revisions 不可修改（immutable snapshot）';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_configuration_revisions_immutable ON configuration_revisions;
CREATE TRIGGER trg_configuration_revisions_immutable
    BEFORE UPDATE ON configuration_revisions
    FOR EACH ROW EXECUTE FUNCTION prevent_configuration_revision_update();

-- configurations.current_revision_id -> configuration_revisions.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'configurations_current_revision_id_fkey'
    ) THEN
        ALTER TABLE configurations
            ADD CONSTRAINT configurations_current_revision_id_fkey
            FOREIGN KEY (current_revision_id)
            REFERENCES configuration_revisions(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- ############################################################
-- PART 4: RLS 与权限（成员可读本租户，管理员可写；跨租户不可见）
-- ############################################################

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE configurations ENABLE ROW LEVEL SECURITY;
ALTER TABLE configuration_revisions ENABLE ROW LEVEL SECURITY;

-- 收回默认授予 anon/authenticated 的全部权限，再按最小权限授予
REVOKE ALL ON projects FROM anon, authenticated;
REVOKE ALL ON configurations FROM anon, authenticated;
REVOKE ALL ON configuration_revisions FROM anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON projects TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON configurations TO authenticated;
-- Revision 只读：写入仅由 service_role 在发布流程中完成
GRANT SELECT ON configuration_revisions TO authenticated;
GRANT ALL ON projects, configurations, configuration_revisions TO service_role;

-- 4.1 projects
DROP POLICY IF EXISTS "Tenant members can view projects" ON projects;
CREATE POLICY "Tenant members can view projects" ON projects
    FOR SELECT USING (
        tenant_id = get_current_user_tenant_id()
        OR get_current_user_role() = 'super_admin'
    );

DROP POLICY IF EXISTS "Tenant admins can manage projects" ON projects;
CREATE POLICY "Tenant admins can manage projects" ON projects
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

DROP POLICY IF EXISTS "Service role full access to projects" ON projects;
CREATE POLICY "Service role full access to projects" ON projects
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- 4.2 configurations
DROP POLICY IF EXISTS "Tenant members can view configurations" ON configurations;
CREATE POLICY "Tenant members can view configurations" ON configurations
    FOR SELECT USING (
        tenant_id = get_current_user_tenant_id()
        OR get_current_user_role() = 'super_admin'
    );

DROP POLICY IF EXISTS "Tenant admins can manage configurations" ON configurations;
CREATE POLICY "Tenant admins can manage configurations" ON configurations
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

DROP POLICY IF EXISTS "Service role full access to configurations" ON configurations;
CREATE POLICY "Service role full access to configurations" ON configurations
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- 4.3 configuration_revisions（租户隔离经由所属 configuration）
DROP POLICY IF EXISTS "Tenant members can view configuration_revisions" ON configuration_revisions;
CREATE POLICY "Tenant members can view configuration_revisions" ON configuration_revisions
    FOR SELECT USING (
        get_current_user_role() = 'super_admin'
        OR configuration_id IN (
            SELECT id FROM configurations
            WHERE tenant_id = get_current_user_tenant_id()
        )
    );

DROP POLICY IF EXISTS "Service role full access to configuration_revisions" ON configuration_revisions;
CREATE POLICY "Service role full access to configuration_revisions" ON configuration_revisions
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ############################################################
-- PART 5: 旧模板定义 -> Configuration definition 映射函数
-- ############################################################
-- 与 services/configuration_service.py:build_definition_from_template 保持同构。
-- 迁移时快照模板的字段、示例、prompt、提取模式、Excel/飞书输出元数据。

CREATE OR REPLACE FUNCTION build_legacy_template_definition(p_template_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
    SELECT jsonb_build_object(
        'fields', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'field_key', f.field_key,
                'field_label', f.field_label,
                'field_type', f.field_type,
                'extraction_hint', f.extraction_hint,
                'feishu_column', f.feishu_column,
                'sort_order', f.sort_order,
                'review_enforced', f.review_enforced,
                'review_allowed_values', f.review_allowed_values,
                'is_required', f.is_required,
                'default_value', f.default_value,
                'source_doc_type', f.source_doc_type
            ) ORDER BY f.sort_order, f.field_key)
            FROM template_fields f
            WHERE f.template_id = t.id
        ), '[]'::jsonb),
        'examples', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'example_input', e.example_input,
                'example_output', e.example_output,
                'description', e.description,
                'sort_order', e.sort_order,
                'is_active', e.is_active
            ) ORDER BY e.sort_order, e.created_at)
            FROM template_examples e
            WHERE e.template_id = t.id
        ), '[]'::jsonb),
        'extraction_prompt', t.extraction_prompt_template,
        'extraction_mode', t.extraction_mode,
        'per_page_extraction', t.per_page_extraction,
        'cleaner_module', t.cleaner_module,
        'output_mode', t.output_mode,
        'push_attachment', t.push_attachment,
        'auto_approve', t.auto_approve,
        'feishu', jsonb_build_object(
            'bitable_token', t.feishu_bitable_token,
            'table_id', t.feishu_table_id
        ),
        'excel', jsonb_build_object(
            'file_name', t.excel_template_file_name,
            'path', t.excel_template_path,
            'placeholders', COALESCE(t.excel_template_placeholders, '[]'::jsonb)
        )
    )
    FROM document_templates t
    WHERE t.id = p_template_id;
$$;

-- ############################################################
-- PART 6: 数据迁移（幂等）
-- ############################################################

-- 6.1 每个租户一个默认项目
INSERT INTO projects (tenant_id, name, description, is_default)
SELECT t.id, '默认项目', '租户默认项目（Configuration 的默认归属）', TRUE
FROM tenants t
WHERE NOT EXISTS (
    SELECT 1 FROM projects p
    WHERE p.tenant_id = t.id AND p.is_default
);

-- 6.2 模板 -> 已发布 Configuration（按 legacy_template_id 去重）
INSERT INTO configurations (
    tenant_id, project_id, name, code, description, type, status,
    draft_definition, legacy_template_id, created_at, updated_at
)
SELECT
    t.tenant_id,
    p.id,
    t.name,
    t.code,
    t.description,
    'extract',
    'published',
    build_legacy_template_definition(t.id),
    t.id,
    t.created_at,
    t.updated_at
FROM document_templates t
JOIN projects p ON p.tenant_id = t.tenant_id AND p.is_default
WHERE NOT EXISTS (
    SELECT 1 FROM configurations c WHERE c.legacy_template_id = t.id
);

-- 6.3 每个迁移配置生成第 1 个 Revision（快照）
INSERT INTO configuration_revisions (
    configuration_id, revision_number, definition, created_at, published_at
)
SELECT
    c.id,
    1,
    build_legacy_template_definition(c.legacy_template_id),
    c.created_at,
    c.created_at
FROM configurations c
WHERE c.legacy_template_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM configuration_revisions r WHERE r.configuration_id = c.id
  )
ON CONFLICT (configuration_id, revision_number) DO NOTHING;

-- 6.4 指向当前 Revision
UPDATE configurations c
SET current_revision_id = r.id
FROM configuration_revisions r
WHERE r.configuration_id = c.id
  AND c.current_revision_id IS NULL;

SELECT pg_notify('pgrst', 'reload schema');
SELECT '021: Project / Configuration / Configuration Revision 就绪，旧模板数据已迁移' AS message;
