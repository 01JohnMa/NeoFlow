-- ============================================================
-- MIGRATION 013: tenants 表新增 settings JSONB 列
-- 用于存储部门级配置，如 paired_batch_mode
-- ============================================================

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS settings JSONB NOT NULL DEFAULT '{}';

COMMENT ON COLUMN tenants.settings IS '部门级配置，如 {"paired_batch_mode": true}';
