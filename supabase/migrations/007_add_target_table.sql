-- ============================================================
-- MIGRATION 007: 新增 target_table、paired_document_id、merge_template_id
-- ============================================================
-- 1. document_templates 增加 target_table 列
--    让每个模板自己声明提取结果写入哪张业务表，消除 Python 侧硬编码映射
-- 2. documents 增加配对字段，支持 merge 模式的双文档审核联动

-- 1. document_templates.target_table
ALTER TABLE document_templates
    ADD COLUMN IF NOT EXISTS target_table VARCHAR(100);

-- 回填现有模板（按 code 匹配）
UPDATE document_templates SET target_table = 'inspection_reports'
    WHERE code = 'inspection_report';

UPDATE document_templates SET target_table = 'expresses'
    WHERE code = 'express';

UPDATE document_templates SET target_table = 'sampling_forms'
    WHERE code IN ('sampling', 'sampling_form');

UPDATE document_templates SET target_table = 'packagings'
    WHERE code = 'packaging';

UPDATE document_templates SET target_table = 'integrating_sphere_reports'
    WHERE code IN ('integrating_sphere', '积分球测试');

UPDATE document_templates SET target_table = 'light_distribution_reports'
    WHERE code IN ('light_distribution', '光分布测试');

UPDATE document_templates SET target_table = 'lighting_reports'
    WHERE code IN ('lighting_combined');

-- 2. documents 配对字段
--    paired_document_id: merge 模式中 A 指向 B，B 指向 A（多样品时 B 指向第一个 A）
--    merge_template_id:  记录用哪个合并模板推送飞书
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS paired_document_id UUID REFERENCES documents(id),
    ADD COLUMN IF NOT EXISTS merge_template_id  UUID REFERENCES document_templates(id);

CREATE INDEX IF NOT EXISTS idx_documents_paired_document_id
    ON documents(paired_document_id);
