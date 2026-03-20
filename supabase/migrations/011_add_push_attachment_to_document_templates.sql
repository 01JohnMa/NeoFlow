-- ============================================================
-- MIGRATION 011: 为 document_templates 补充 push_attachment 字段
-- ============================================================
-- 兼容历史环境：早期库若未执行包含该列的初始化脚本，
-- 管理端保存模板配置时会因缺少 push_attachment 列而失败。
--
-- 该字段用于控制审核推送飞书时，是否同步上传原始文件作为附件。
-- ============================================================

ALTER TABLE document_templates
    ADD COLUMN IF NOT EXISTS push_attachment BOOLEAN DEFAULT TRUE;

COMMENT ON COLUMN document_templates.push_attachment IS
    '审核推送飞书时是否同步上传原始文件到附件列';

SELECT pg_notify('pgrst', 'reload schema');
SELECT '011: document_templates.push_attachment 字段补充完成' AS message;
