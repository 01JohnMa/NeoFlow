-- ============================================================
-- Auth 服务启动后执行的脚本
-- ============================================================
-- 【重要】此脚本需要在 auth 服务完全启动后手动执行
-- 执行命令：
--   Windows PowerShell:
--     Get-Content supabase/migrations/003_post_auth_setup.sql | docker exec -i supabase-db psql -U postgres -d postgres
--   Linux/Mac:
--     docker exec -i supabase-db psql -U postgres -d postgres < supabase/migrations/003_post_auth_setup.sql
-- ============================================================

-- ############################################################
-- PART 1: 创建 auth.users 触发器
-- ############################################################

-- 确保 handle_new_user 函数存在（由 001_multi_tenant.sql 创建）
-- 当新用户注册时，自动创建 profile 记录

DO $$
BEGIN
    -- 检查 auth.users 表是否存在
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables 
                   WHERE table_schema = 'auth' AND table_name = 'users') THEN
        RAISE EXCEPTION 'auth.users 表不存在，请确保 auth 服务已启动';
    END IF;
    
    -- 检查 handle_new_user 函数是否存在
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'handle_new_user') THEN
        RAISE EXCEPTION 'handle_new_user 函数不存在，请先执行 001_multi_tenant.sql';
    END IF;
    
    -- 删除旧触发器（如果存在）
    DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
    
    -- 创建新触发器
    CREATE TRIGGER on_auth_user_created
        AFTER INSERT ON auth.users
        FOR EACH ROW EXECUTE FUNCTION handle_new_user();
    
    RAISE NOTICE 'auth.users 触发器创建成功！';
END $$;

-- ############################################################
-- 完成
-- ############################################################

SELECT '003_post_auth_setup.sql: auth 触发器创建完成！' as message;
SELECT '新用户注册时将自动创建 profile 记录' as note;
