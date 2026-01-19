-- ============================================================
-- 现有数据迁移脚本
-- ============================================================
-- 功能：将现有用户和文档归属到质量运营部
-- 执行顺序：在 007_init_tenant_data.sql 之后执行
-- ============================================================

-- ############################################################
-- PART 1: 迁移现有用户到质量运营部
-- ############################################################

-- 1.1 为所有现有用户创建 profile（如果不存在）
-- 并将他们归属到质量运营部
INSERT INTO profiles (id, tenant_id, role, display_name)
SELECT 
    u.id,
    'a0000000-0000-0000-0000-000000000001',  -- 质量运营部 tenant_id
    'user',
    COALESCE(u.raw_user_meta_data->>'display_name', u.email)
FROM auth.users u
WHERE NOT EXISTS (
    SELECT 1 FROM profiles p WHERE p.id = u.id
);

-- 1.2 更新已有但没有 tenant_id 的 profile
UPDATE profiles 
SET tenant_id = 'a0000000-0000-0000-0000-000000000001'
WHERE tenant_id IS NULL;


-- ############################################################
-- PART 2: 迁移现有文档到质量运营部
-- ############################################################

-- 2.1 更新所有没有 tenant_id 的文档，归属到质量运营部
UPDATE documents 
SET tenant_id = 'a0000000-0000-0000-0000-000000000001'
WHERE tenant_id IS NULL;

-- 2.2 根据文档类型设置对应的 template_id
-- 测试单/检验报告
UPDATE documents 
SET template_id = 'b0000000-0000-0000-0000-000000000001'
WHERE document_type IN ('测试单', '检验报告', '检测报告')
  AND template_id IS NULL
  AND tenant_id = 'a0000000-0000-0000-0000-000000000001';

-- 快递单
UPDATE documents 
SET template_id = 'b0000000-0000-0000-0000-000000000002'
WHERE document_type = '快递单'
  AND template_id IS NULL
  AND tenant_id = 'a0000000-0000-0000-0000-000000000001';

-- 抽样单
UPDATE documents 
SET template_id = 'b0000000-0000-0000-0000-000000000003'
WHERE document_type = '抽样单'
  AND template_id IS NULL
  AND tenant_id = 'a0000000-0000-0000-0000-000000000001';


-- ############################################################
-- PART 3: 创建第一个超级管理员（如有需要手动执行）
-- ############################################################

-- 注意：此命令需要知道具体的用户 ID，请根据实际情况修改
-- 示例：将某用户设为超级管理员
-- UPDATE profiles 
-- SET role = 'super_admin'
-- WHERE id = '用户ID';

-- 或者按邮箱查找并更新
-- UPDATE profiles p
-- SET role = 'super_admin'
-- FROM auth.users u
-- WHERE p.id = u.id AND u.email = 'admin@example.com';


-- ############################################################
-- PART 4: 统计迁移结果
-- ############################################################

SELECT '008_migrate_existing_data.sql: 数据迁移完成！' as message;

-- 统计迁移的用户数
SELECT 
    t.name as tenant_name,
    COUNT(p.id) as user_count
FROM profiles p
LEFT JOIN tenants t ON p.tenant_id = t.id
GROUP BY t.name;

-- 统计迁移的文档数
SELECT 
    t.name as tenant_name,
    dt.name as template_name,
    COUNT(d.id) as document_count
FROM documents d
LEFT JOIN tenants t ON d.tenant_id = t.id
LEFT JOIN document_templates dt ON d.template_id = dt.id
GROUP BY t.name, dt.name
ORDER BY t.name, dt.name;
