-- ============================================================
-- 修复 profiles 表 tenant_id - 从 auth.users 的 raw_user_meta_data 同步
-- ============================================================
-- 问题：原 handle_new_user 触发器未保存用户注册时传入的 tenant_id
-- 修复：1. 更新触发器函数  2. 同步已有用户的 tenant_id
-- ============================================================

-- PART 1: 更新触发器函数，支持保存 tenant_id
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
    v_tenant_id UUID;
BEGIN
    -- 从 raw_user_meta_data 中获取 tenant_id（注册时传入）
    v_tenant_id := (NEW.raw_user_meta_data->>'tenant_id')::UUID;
    
    INSERT INTO public.profiles (id, tenant_id, role, display_name)
    VALUES (
        NEW.id,
        v_tenant_id,
        'user',
        COALESCE(NEW.raw_user_meta_data->>'display_name', NEW.email)
    );
    RETURN NEW;
EXCEPTION WHEN invalid_text_representation THEN
    -- 如果 tenant_id 格式无效，忽略它
    INSERT INTO public.profiles (id, role, display_name)
    VALUES (
        NEW.id,
        'user',
        COALESCE(NEW.raw_user_meta_data->>'display_name', NEW.email)
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- PART 2: 修复已有用户的 tenant_id（从 auth.users 同步）
UPDATE public.profiles p
SET tenant_id = (u.raw_user_meta_data->>'tenant_id')::UUID
FROM auth.users u
WHERE p.id = u.id
  AND p.tenant_id IS NULL
  AND u.raw_user_meta_data->>'tenant_id' IS NOT NULL
  AND u.raw_user_meta_data->>'tenant_id' != '';

-- 完成
SELECT '011_fix_profile_tenant_id.sql: profiles 表 tenant_id 修复完成！' as message;
