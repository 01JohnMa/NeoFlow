-- ============================================================
-- 照明综合报告表和合并文档关联
-- ============================================================
-- 功能：
-- 1. 创建 lighting_reports 表存储照明综合报告提取结果
-- 2. documents 表添加 source_document_ids 字段用于关联原始文档
-- 3. 隐藏子模板（积分球测试、光分布测试）
-- ============================================================

-- ############################################################
-- PART 1: 创建照明综合报告提取结果表
-- ############################################################

CREATE TABLE IF NOT EXISTS lighting_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 来自积分球（14个字段）
    sample_model VARCHAR(255),              -- 样品型号
    chromaticity_x VARCHAR(64),             -- 色品坐标X
    chromaticity_y VARCHAR(64),             -- 色品坐标Y
    duv VARCHAR(64),                        -- duv
    cct VARCHAR(64),                        -- 色温(CCT)
    ra VARCHAR(64),                         -- Ra
    r9 VARCHAR(64),                         -- R9
    cqs VARCHAR(64),                        -- CQS
    sdcm VARCHAR(64),                       -- 色容差SDCM
    power_sphere VARCHAR(64),               -- 功率(积分球)
    luminous_flux_sphere VARCHAR(64),       -- 光通量(积分球)
    luminous_efficacy_sphere VARCHAR(64),   -- 光效(积分球)
    rf VARCHAR(64),                         -- Rf
    rg VARCHAR(64),                         -- Rg
    
    -- 来自光分布（6个字段）
    lamp_specification VARCHAR(255),        -- 灯具规格
    power VARCHAR(64),                      -- 功率
    luminous_flux VARCHAR(64),              -- 光通量(光分布)
    luminous_efficacy VARCHAR(64),          -- 光效(光分布)
    peak_intensity VARCHAR(64),             -- 峰值光强
    beam_angle VARCHAR(64),                 -- 光束角
    
    -- 元数据
    extraction_confidence FLOAT,
    extraction_version VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data JSONB,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_by UUID,
    validated_at TIMESTAMP WITH TIME ZONE,
    validation_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT lighting_reports_document_unique UNIQUE(document_id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_lighting_reports_document_id ON lighting_reports(document_id);
CREATE INDEX IF NOT EXISTS idx_lighting_reports_sample_model ON lighting_reports(sample_model);

-- 创建更新时间触发器
DROP TRIGGER IF EXISTS update_lighting_reports_updated_at ON lighting_reports;
CREATE TRIGGER update_lighting_reports_updated_at 
    BEFORE UPDATE ON lighting_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 启用 RLS
ALTER TABLE lighting_reports ENABLE ROW LEVEL SECURITY;

-- RLS 策略：用户可以查看自己文档的照明报告
DROP POLICY IF EXISTS "用户可以查看自己文档的照明报告" ON lighting_reports;
CREATE POLICY "用户可以查看自己文档的照明报告" ON lighting_reports
    FOR ALL USING (
        document_id IN (SELECT id FROM documents WHERE user_id = auth.uid())
    );

-- RLS 策略：Service role 完全访问
DROP POLICY IF EXISTS "Service role can manage all lighting_reports" ON lighting_reports;
CREATE POLICY "Service role can manage all lighting_reports" ON lighting_reports
    FOR ALL USING (auth.role() = 'service_role');

-- RLS 策略：管理员可以查看所有照明报告
DROP POLICY IF EXISTS "管理员可以查看所有照明报告" ON lighting_reports;
CREATE POLICY "管理员可以查看所有照明报告" ON lighting_reports
    FOR ALL USING (
        (auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true
    );


-- ############################################################
-- PART 2: documents 表添加合并文档关联字段
-- ############################################################

-- 添加 source_document_ids 字段：合并文档关联的原始文档ID列表
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_document_ids UUID[];

-- 创建索引（GIN索引用于数组查询）
CREATE INDEX IF NOT EXISTS idx_documents_source_document_ids ON documents USING GIN (source_document_ids);


-- ############################################################
-- PART 3: 隐藏子模板（前端不显示）
-- ############################################################
-- 将"积分球测试"和"光分布测试"子模板设为不可见
-- 前端只显示"照明综合报告"合并模板

UPDATE document_templates 
SET is_active = FALSE 
WHERE code IN ('integrating_sphere', 'light_distribution');


-- ############################################################
-- 完成
-- ############################################################

SELECT '009_lighting_reports.sql: 照明综合报告表创建完成！' as message;
SELECT '- lighting_reports 表已创建（20个提取字段）' as detail1;
SELECT '- documents.source_document_ids 字段已添加' as detail2;
SELECT '- 子模板（积分球测试、光分布测试）已隐藏' as detail3;
