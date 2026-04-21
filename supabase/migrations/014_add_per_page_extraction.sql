-- ============================================================
-- MIGRATION 014: document_templates 新增 per_page_extraction 列
-- 控制逐页提取模式：开启后每页独立提取为一个样品记录
-- ============================================================

ALTER TABLE document_templates
    ADD COLUMN IF NOT EXISTS per_page_extraction BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN document_templates.per_page_extraction IS '逐页提取模式：true 时每页独立提取为一个样品记录';
