-- ============================================================
-- MIGRATION 031: GoTrue 动态注册用户的 instance_id 兼容
-- ============================================================
-- 外置 PostgreSQL profile 可能由较旧的 GoTrue 表结构创建 auth.users，
-- instance_id 允许 NULL 且没有默认值。GoTrue v2.143 的邮箱重复检查
-- 按 instance_id 查询，导致新注册返回 Database error finding user。

DO $$
BEGIN
    IF to_regclass('auth.users') IS NOT NULL THEN
        ALTER TABLE auth.users
            ALTER COLUMN instance_id SET DEFAULT '00000000-0000-0000-0000-000000000000';

        UPDATE auth.users
        SET instance_id = '00000000-0000-0000-0000-000000000000'
        WHERE instance_id IS NULL;
    END IF;
END $$;

SELECT pg_notify('pgrst', 'reload schema');
SELECT '031: auth.users instance_id default/backfill ready' AS message;
