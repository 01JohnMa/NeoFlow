-- ============================================================
-- MIGRATION 007: 新增 target_table
-- ============================================================
-- document_templates 增加 target_table 列
--    让每个模板自己声明提取结果写入哪张业务表，消除 Python 侧硬编码映射

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
