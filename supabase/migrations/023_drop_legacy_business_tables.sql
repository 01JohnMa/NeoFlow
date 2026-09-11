-- ============================================================
-- MIGRATION 023: 删除旧业务结果表、动态 DDL 与业务映射
-- ============================================================
-- M2 收尾：Result 已接管全部读写，旧形态整体下线。
--
-- 本迁移删除：
--   1. 业务结果物理表及其历史数据（检测报告/快递单/抽样单/包装/照明类）
--   2. migration 005 的动态 schema sync 函数（ADD/RENAME/DROP COLUMN、
--      查询列名）
--   3. migration 021 的旧模板 -> definition 映射函数
--   4. 旧模板表 document_templates / template_fields / template_examples
--   5. documents.template_id 对 document_templates 的外键（列保留，
--      现在存 Configuration 引用：新值为 configurations.id，
--      历史值为 configurations.legacy_template_id）
--   6. paired-batch 遗留的 tenants.settings 列
--
-- 幂等性：全部使用 IF EXISTS / CASCADE，可重复执行。
-- 执行顺序：先删函数与外键，再删表，避免依赖报错。
-- ============================================================

-- ############################################################
-- PART 1: 动态 DDL 与旧模板映射函数
-- ############################################################

DROP FUNCTION IF EXISTS add_result_column(TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS rename_result_column(TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS drop_result_column(TEXT, TEXT, BOOLEAN);
DROP FUNCTION IF EXISTS get_result_table_columns(TEXT);
DROP FUNCTION IF EXISTS build_legacy_template_definition(UUID);

-- ############################################################
-- PART 2: documents.template_id 外键（列保留为 Configuration 引用）
-- ############################################################

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_template_id_fkey;

COMMENT ON COLUMN documents.template_id IS
    'Configuration 引用：新值为 configurations.id，历史值为 configurations.legacy_template_id';

-- ############################################################
-- PART 3: 业务结果物理表与历史数据
-- ############################################################

DROP TABLE IF EXISTS inspection_reports CASCADE;
DROP TABLE IF EXISTS expresses CASCADE;
DROP TABLE IF EXISTS sampling_forms CASCADE;
DROP TABLE IF EXISTS packagings CASCADE;
DROP TABLE IF EXISTS lighting_reports CASCADE;
DROP TABLE IF EXISTS integrating_sphere_reports CASCADE;
DROP TABLE IF EXISTS light_distribution_reports CASCADE;

-- ############################################################
-- PART 4: 旧模板表（Configuration/Revision 已接管定义）
-- ############################################################

DROP TABLE IF EXISTS template_examples CASCADE;
DROP TABLE IF EXISTS template_fields CASCADE;
DROP TABLE IF EXISTS document_templates CASCADE;

-- ############################################################
-- PART 5: paired-batch 遗留的租户级设置列
-- ############################################################

ALTER TABLE tenants DROP COLUMN IF EXISTS settings;

-- ############################################################
-- PART 6: 通知 PostgREST 刷新 schema 缓存
-- ############################################################

SELECT pg_notify('pgrst', 'reload schema');
SELECT '023: 旧业务表、动态 DDL 与模板表已删除' AS message;
