-- ============ 用户权限设置 ============
UPDATE auth.users SET raw_app_meta_data = '{"is_admin":true}' WHERE email = '你的邮箱';

-- Docker 命令方式
-- docker exec -i supabase-db psql -U postgres -d postgres -c "
-- UPDATE auth.users
-- SET raw_app_meta_data = jsonb_build_object('is_admin', true)
-- WHERE email = '980147736@qq.com';
-- "

-- ============ 修复 sampling_forms 表缺失列 ============
-- 如果遇到 "Column 'manufacturer' does not exist" 错误，执行以下 SQL：
ALTER TABLE sampling_forms ADD COLUMN IF NOT EXISTS manufacturer VARCHAR(255);