-- 009_cleanup_process_mode.sql
-- 删除 process_mode 列和 template_merge_rules 表
-- 前置条件：所有代码中对 process_mode 和 template_merge_rules 的引用已全部清除

-- 删除 process_mode 列
ALTER TABLE document_templates DROP COLUMN IF EXISTS process_mode;

-- 删除 template_merge_rules 表（RLS 策略和触发器会自动级联删除）
DROP TABLE IF EXISTS template_merge_rules CASCADE;
