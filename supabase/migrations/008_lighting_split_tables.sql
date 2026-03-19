-- ============================================================
-- MIGRATION 008: 拆分 lighting_reports 为两张独立表
-- integrating_sphere_reports：积分球专用（14字段）
-- light_distribution_reports：光分布专用（8字段）
-- lighting_reports 保留，不再写入新数据
-- ============================================================

-- 1. 积分球报告表
CREATE TABLE IF NOT EXISTS integrating_sphere_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,

    -- 积分球字段（14个）
    sample_model              VARCHAR(255),   -- 样品型号
    chromaticity_x            VARCHAR(64),    -- 色品坐标X
    chromaticity_y            VARCHAR(64),    -- 色品坐标Y
    duv                       VARCHAR(64),    -- duv
    cct                       VARCHAR(64),    -- 色温(CCT)
    ra                        VARCHAR(64),    -- Ra
    r9                        VARCHAR(64),    -- R9
    cqs                       VARCHAR(64),    -- CQS
    sdcm                      VARCHAR(64),    -- 色容差SDCM
    power_sphere              VARCHAR(64),    -- 功率(积分球)
    luminous_flux_sphere      VARCHAR(64),    -- 光通量(积分球)
    luminous_efficacy_sphere  VARCHAR(64),    -- 光效(积分球)
    rf                        VARCHAR(64),    -- Rf
    rg                        VARCHAR(64),    -- Rg

    -- 元数据
    extraction_confidence FLOAT,
    extraction_version    VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data   JSONB,
    is_validated          BOOLEAN DEFAULT FALSE,
    validated_by          UUID,
    validated_at          TIMESTAMP WITH TIME ZONE,
    validation_notes      TEXT,
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT integrating_sphere_reports_document_unique UNIQUE(document_id)
);

-- 2. 光分布报告表
CREATE TABLE IF NOT EXISTS light_distribution_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,

    -- 光分布字段（8个）
    c0_180             VARCHAR(64),    -- C0/180
    c90_270            VARCHAR(64),    -- C90/270
    avg_beam_angle     VARCHAR(64),    -- 平均光束角
    lamp_specification VARCHAR(255),   -- 灯具规格
    power              VARCHAR(64),    -- 功率
    luminous_flux      VARCHAR(64),    -- 光通量(光分布)
    luminous_efficacy  VARCHAR(64),    -- 光效(光分布)
    peak_intensity     VARCHAR(64),    -- 峰值光强

    -- 元数据
    extraction_confidence FLOAT,
    extraction_version    VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data   JSONB,
    is_validated          BOOLEAN DEFAULT FALSE,
    validated_by          UUID,
    validated_at          TIMESTAMP WITH TIME ZONE,
    validation_notes      TEXT,
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT light_distribution_reports_document_unique UNIQUE(document_id)
);

-- 3. 索引
CREATE INDEX IF NOT EXISTS idx_integrating_sphere_reports_document_id
    ON integrating_sphere_reports(document_id);
CREATE INDEX IF NOT EXISTS idx_integrating_sphere_reports_sample_model
    ON integrating_sphere_reports(sample_model);
CREATE INDEX IF NOT EXISTS idx_light_distribution_reports_document_id
    ON light_distribution_reports(document_id);

-- 4. 更新触发器
DROP TRIGGER IF EXISTS update_integrating_sphere_reports_updated_at ON integrating_sphere_reports;
CREATE TRIGGER update_integrating_sphere_reports_updated_at
    BEFORE UPDATE ON integrating_sphere_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_light_distribution_reports_updated_at ON light_distribution_reports;
CREATE TRIGGER update_light_distribution_reports_updated_at
    BEFORE UPDATE ON light_distribution_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 5. RLS
ALTER TABLE integrating_sphere_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE light_distribution_reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role can manage all integrating_sphere_reports" ON integrating_sphere_reports;
CREATE POLICY "Service role can manage all integrating_sphere_reports"
    ON integrating_sphere_reports FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "Service role can manage all light_distribution_reports" ON light_distribution_reports;
CREATE POLICY "Service role can manage all light_distribution_reports"
    ON light_distribution_reports FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "管理员可以查看所有积分球报告" ON integrating_sphere_reports;
CREATE POLICY "管理员可以查看所有积分球报告" ON integrating_sphere_reports
    FOR ALL USING ((auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true);

DROP POLICY IF EXISTS "管理员可以查看所有光分布报告" ON light_distribution_reports;
CREATE POLICY "管理员可以查看所有光分布报告" ON light_distribution_reports
    FOR ALL USING ((auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true);

-- 6. 更新 target_table 指向新表
UPDATE document_templates
    SET target_table = 'integrating_sphere_reports'
    WHERE code IN ('integrating_sphere', '积分球测试');

UPDATE document_templates
    SET target_table = 'light_distribution_reports'
    WHERE code IN ('light_distribution', '光分布测试');

-- 7. 通知 PostgREST 刷新 schema 缓存
SELECT pg_notify('pgrst', 'reload schema');

SELECT '008: integrating_sphere_reports + light_distribution_reports 创建完成' AS message;
