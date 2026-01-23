-- 012_unify_inspection_report.sql
-- 统一"检测报告"命名
-- 执行: Get-Content supabase/migrations/012_unify_inspection_report.sql | docker exec -i supabase-db psql -U postgres

-- 1. 将模板名称从"检验报告"改为"检测报告"
UPDATE document_templates 
SET name = '检测报告' 
WHERE code = 'inspection_report';

-- 2. 将历史文档类型统一为"检测报告"
UPDATE documents 
SET document_type = '检测报告' 
WHERE document_type IN ('测试单', '检验报告') 
  AND document_type != '检测报告';

-- 验证
SELECT '模板更新完成' as message, name, code FROM document_templates WHERE code = 'inspection_report';
SELECT '文档类型统计' as message, document_type, count(*) FROM documents GROUP BY document_type;
