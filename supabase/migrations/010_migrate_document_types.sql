-- ============================================================
-- 文档类型数据迁移脚本
-- ============================================================
-- 功能：将旧的中文 document_type 统一迁移为模板 code 格式
-- 目的：降低系统耦合性，统一使用 code 作为文档类型标识
-- 执行时机：在代码修改部署后执行
-- ============================================================

-- ############################################################
-- PART 1: 迁移 documents 表的 document_type 字段
-- ############################################################

-- 1.1 检测报告相关（统一为 inspection_report）
UPDATE documents 
SET document_type = 'inspection_report' 
WHERE document_type IN ('测试单', '检验报告', '检测报告')
  AND document_type != 'inspection_report';

-- 1.2 抽样单相关（统一为 sampling，与模板 code 一致）
UPDATE documents 
SET document_type = 'sampling' 
WHERE document_type IN ('抽样单', 'sampling_form')
  AND document_type != 'sampling';

-- 1.3 快递单相关（统一为 express）
UPDATE documents 
SET document_type = 'express' 
WHERE document_type = '快递单'
  AND document_type != 'express';

-- 1.4 照明综合报告相关（统一为 lighting_combined）
UPDATE documents 
SET document_type = 'lighting_combined' 
WHERE document_type = '照明综合报告'
  AND document_type != 'lighting_combined';

-- ############################################################
-- PART 2: 验证迁移结果
-- ############################################################

-- 查看迁移后的 document_type 分布
SELECT document_type, COUNT(*) as count 
FROM documents 
WHERE document_type IS NOT NULL 
GROUP BY document_type 
ORDER BY count DESC;

-- ############################################################
-- 完成
-- ############################################################

SELECT '010_migrate_document_types.sql: 文档类型迁移完成！' as message;
