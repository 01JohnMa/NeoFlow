-- ============================================================
-- 包装模板新增字段：产品特点（product_characteristics）
-- ============================================================
-- 背景：
-- 该字段可在模板配置页新增，但 packagings 表没有对应列时，
-- 审核结果落库会丢失该字段（仅保留在 raw_extraction_data）。
--
-- 目标：
-- 为 packagings 表补充 product_characteristics 列，支持持久化与查询展示。
-- ============================================================

ALTER TABLE IF EXISTS packagings
ADD COLUMN IF NOT EXISTS product_characteristics TEXT;

