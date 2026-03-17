-- ============================================================
-- 模板级提取引擎选择：extraction_mode
-- ============================================================
-- 每个模板可独立选择 OCR+LLM 或 VLM 多模态处理模式。
-- 与已有的 process_mode（'single'/'merge'）互不干扰。
-- ============================================================

ALTER TABLE document_templates
ADD COLUMN IF NOT EXISTS extraction_mode VARCHAR(20) DEFAULT 'ocr_llm'
CHECK (extraction_mode IN ('ocr_llm', 'vlm'));

COMMENT ON COLUMN document_templates.extraction_mode IS
    '提取引擎：ocr_llm=PaddleOCR+LLM（印刷体），vlm=多模态VLM（手写/复杂版式）';
