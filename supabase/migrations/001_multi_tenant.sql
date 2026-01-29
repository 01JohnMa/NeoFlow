-- ============================================================
-- 多租户配置化系统 - 数据库迁移脚本
-- ============================================================
-- 功能：支持多部门（质量运营、照明事业部等）使用同一系统
-- 包含：租户表、文档模板表、模板字段表、模板示例表、合并规则表
-- ============================================================

-- ############################################################
-- PART 0: 修复表所有权问题（确保 postgres 角色可以操作）
-- ############################################################
-- 说明：Supabase 中某些表可能由 supabase_admin 创建，
-- 需要将所有权转给 postgres 才能执行 ALTER TABLE 和 RLS 策略修改

DO $$
BEGIN
    -- 修改 documents 表所有权（如果表存在）
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'documents') THEN
        EXECUTE 'ALTER TABLE documents OWNER TO postgres';
        RAISE NOTICE 'documents 表所有权已转给 postgres';
    END IF;
    
    -- 修改 extraction_logs 表所有权（如果表存在）
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'extraction_logs') THEN
        EXECUTE 'ALTER TABLE extraction_logs OWNER TO postgres';
        RAISE NOTICE 'extraction_logs 表所有权已转给 postgres';
    END IF;
END $$;

-- ############################################################
-- PART 1: 创建多租户基础表
-- ############################################################

-- 1.1 租户表 (tenants)
-- 存储部门基础信息，飞书应用凭证共用（保留在 settings.py）
CREATE TABLE IF NOT EXISTS tenants (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(100) NOT NULL,           -- 租户名称，如"质量运营部"
    code VARCHAR(50) UNIQUE NOT NULL,     -- 租户代码，如"quality"
    description TEXT,                     -- 描述
    is_active BOOLEAN DEFAULT TRUE,       -- 是否启用
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 1.2 文档模板表 (document_templates)
-- 每个租户可配置多个文档模板
CREATE TABLE IF NOT EXISTS document_templates (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,           -- 模板名称，如"测试单"
    code VARCHAR(50) NOT NULL,            -- 模板代码，如"inspection_report"
    description TEXT,                     -- 描述
    process_mode VARCHAR(20) DEFAULT 'single' CHECK (process_mode IN ('single', 'merge')),
    required_doc_count INT DEFAULT 1,     -- merge模式需要几份文档
    -- 飞书推送配置（每个模板可推送到不同的多维表格）
    feishu_bitable_token VARCHAR(100),    -- 多维表格 app_token
    feishu_table_id VARCHAR(100),         -- 数据表 table_id
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,             -- 排序
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, code)
);

-- 1.3 模板字段表 (template_fields)
-- 定义每个模板需要提取的字段和飞书列映射
CREATE TABLE IF NOT EXISTS template_fields (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    template_id UUID NOT NULL REFERENCES document_templates(id) ON DELETE CASCADE,
    field_key VARCHAR(100) NOT NULL,      -- 字段键名，如"sample_name"
    field_label VARCHAR(100) NOT NULL,    -- 字段显示名，如"样品名称"
    feishu_column VARCHAR(100),           -- 飞书多维表格列名
    field_type VARCHAR(20) DEFAULT 'text' CHECK (field_type IN ('text', 'date', 'number', 'boolean')),
    is_required BOOLEAN DEFAULT FALSE,    -- 是否必填
    default_value TEXT,                   -- 默认值
    source_doc_type VARCHAR(50),          -- merge模式：来自哪种文档类型
    sort_order INT DEFAULT 0,             -- 排序
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(template_id, field_key)
);

-- 1.4 模板示例表 (template_examples) - 存储 few-shot 示例
-- 每个模板可配置多个示例，用于提高 LLM 提取准确率
CREATE TABLE IF NOT EXISTS template_examples (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    template_id UUID NOT NULL REFERENCES document_templates(id) ON DELETE CASCADE,
    example_input TEXT NOT NULL,          -- 示例输入（OCR文本片段）
    example_output JSONB NOT NULL,        -- 示例输出（期望的JSON结果）
    description TEXT,                     -- 示例说明
    sort_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 1.5 合并规则表 (template_merge_rules)
-- 用于照明事业部等需要合并多份文档输出的场景
CREATE TABLE IF NOT EXISTS template_merge_rules (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    template_id UUID NOT NULL REFERENCES document_templates(id) ON DELETE CASCADE,
    doc_type_a VARCHAR(50) NOT NULL,      -- 文档类型A，如"积分球"
    doc_type_b VARCHAR(50) NOT NULL,      -- 文档类型B，如"光分布"
    sub_template_a_id UUID REFERENCES document_templates(id), -- 子模板A
    sub_template_b_id UUID REFERENCES document_templates(id), -- 子模板B
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(template_id)
);

-- ############################################################
-- PART 2: 修改现有表，增加多租户字段
-- ############################################################

-- 2.1 documents 表增加租户和模板关联
ALTER TABLE documents 
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id),
    ADD COLUMN IF NOT EXISTS template_id UUID REFERENCES document_templates(id);

-- 2.2 创建 profiles 表扩展用户信息（Supabase auth.users 不便直接修改）
-- 存储用户的租户关联和角色信息
-- 【注意】移除了对 auth.users 的外键约束，因为初始化时 auth.users 尚不存在
-- 数据一致性通过 handle_new_user 触发器保证
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY,  -- 移除外键，auth.users 由 GoTrue 服务动态创建
    tenant_id UUID REFERENCES tenants(id),
    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('super_admin', 'tenant_admin', 'user')),
    display_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ############################################################
-- PART 3: 创建索引
-- ############################################################

CREATE INDEX IF NOT EXISTS idx_tenants_code ON tenants(code);
CREATE INDEX IF NOT EXISTS idx_tenants_is_active ON tenants(is_active);

CREATE INDEX IF NOT EXISTS idx_document_templates_tenant_id ON document_templates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_document_templates_code ON document_templates(code);
CREATE INDEX IF NOT EXISTS idx_document_templates_is_active ON document_templates(is_active);

CREATE INDEX IF NOT EXISTS idx_template_fields_template_id ON template_fields(template_id);
CREATE INDEX IF NOT EXISTS idx_template_fields_field_key ON template_fields(field_key);

CREATE INDEX IF NOT EXISTS idx_template_examples_template_id ON template_examples(template_id);
CREATE INDEX IF NOT EXISTS idx_template_examples_is_active ON template_examples(is_active);

CREATE INDEX IF NOT EXISTS idx_template_merge_rules_template_id ON template_merge_rules(template_id);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_template_id ON documents(template_id);

CREATE INDEX IF NOT EXISTS idx_profiles_tenant_id ON profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles(role);

-- ############################################################
-- PART 4: 创建触发器（自动更新 updated_at）
-- ############################################################

DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants;
CREATE TRIGGER update_tenants_updated_at 
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_document_templates_updated_at ON document_templates;
CREATE TRIGGER update_document_templates_updated_at 
    BEFORE UPDATE ON document_templates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_template_fields_updated_at ON template_fields;
CREATE TRIGGER update_template_fields_updated_at 
    BEFORE UPDATE ON template_fields
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_template_examples_updated_at ON template_examples;
CREATE TRIGGER update_template_examples_updated_at 
    BEFORE UPDATE ON template_examples
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_template_merge_rules_updated_at ON template_merge_rules;
CREATE TRIGGER update_template_merge_rules_updated_at 
    BEFORE UPDATE ON template_merge_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_profiles_updated_at ON profiles;
CREATE TRIGGER update_profiles_updated_at 
    BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ############################################################
-- PART 5: 启用 RLS 并创建策略
-- ############################################################

-- 5.1 启用 RLS
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE template_fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE template_examples ENABLE ROW LEVEL SECURITY;
ALTER TABLE template_merge_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- 5.2 创建辅助函数：获取当前用户的租户ID
CREATE OR REPLACE FUNCTION get_current_user_tenant_id()
RETURNS UUID AS $$
BEGIN
    RETURN (SELECT tenant_id FROM profiles WHERE id = auth.uid());
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5.3 创建辅助函数：获取当前用户的角色
CREATE OR REPLACE FUNCTION get_current_user_role()
RETURNS VARCHAR AS $$
BEGIN
    RETURN (SELECT role FROM profiles WHERE id = auth.uid());
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5.4 tenants 表 RLS 策略
-- 所有人可以查看启用的租户（注册页需要）
DROP POLICY IF EXISTS "Anyone can view active tenants" ON tenants;
CREATE POLICY "Anyone can view active tenants" ON tenants
    FOR SELECT USING (is_active = TRUE);

-- 超级管理员可以管理所有租户
DROP POLICY IF EXISTS "Super admin can manage all tenants" ON tenants;
CREATE POLICY "Super admin can manage all tenants" ON tenants
    FOR ALL USING (get_current_user_role() = 'super_admin');

-- Service role 完全访问
DROP POLICY IF EXISTS "Service role full access to tenants" ON tenants;
CREATE POLICY "Service role full access to tenants" ON tenants
    FOR ALL USING (auth.role() = 'service_role');

-- 5.5 document_templates 表 RLS 策略
-- 用户可以查看自己租户的模板
DROP POLICY IF EXISTS "Users can view own tenant templates" ON document_templates;
CREATE POLICY "Users can view own tenant templates" ON document_templates
    FOR SELECT USING (
        tenant_id = get_current_user_tenant_id() 
        OR get_current_user_role() = 'super_admin'
    );

-- 租户管理员可以管理自己租户的模板
DROP POLICY IF EXISTS "Tenant admin can manage own tenant templates" ON document_templates;
CREATE POLICY "Tenant admin can manage own tenant templates" ON document_templates
    FOR ALL USING (
        (tenant_id = get_current_user_tenant_id() AND get_current_user_role() IN ('tenant_admin', 'super_admin'))
        OR get_current_user_role() = 'super_admin'
    );

-- Service role 完全访问
DROP POLICY IF EXISTS "Service role full access to document_templates" ON document_templates;
CREATE POLICY "Service role full access to document_templates" ON document_templates
    FOR ALL USING (auth.role() = 'service_role');

-- 5.6 template_fields 表 RLS 策略
DROP POLICY IF EXISTS "Users can view template fields" ON template_fields;
CREATE POLICY "Users can view template fields" ON template_fields
    FOR SELECT USING (
        template_id IN (
            SELECT id FROM document_templates 
            WHERE tenant_id = get_current_user_tenant_id()
        )
        OR get_current_user_role() = 'super_admin'
    );

DROP POLICY IF EXISTS "Service role full access to template_fields" ON template_fields;
CREATE POLICY "Service role full access to template_fields" ON template_fields
    FOR ALL USING (auth.role() = 'service_role');

-- 5.7 template_examples 表 RLS 策略
DROP POLICY IF EXISTS "Users can view template examples" ON template_examples;
CREATE POLICY "Users can view template examples" ON template_examples
    FOR SELECT USING (
        template_id IN (
            SELECT id FROM document_templates 
            WHERE tenant_id = get_current_user_tenant_id()
        )
        OR get_current_user_role() = 'super_admin'
    );

DROP POLICY IF EXISTS "Service role full access to template_examples" ON template_examples;
CREATE POLICY "Service role full access to template_examples" ON template_examples
    FOR ALL USING (auth.role() = 'service_role');

-- 5.8 template_merge_rules 表 RLS 策略
DROP POLICY IF EXISTS "Users can view merge rules" ON template_merge_rules;
CREATE POLICY "Users can view merge rules" ON template_merge_rules
    FOR SELECT USING (
        template_id IN (
            SELECT id FROM document_templates 
            WHERE tenant_id = get_current_user_tenant_id()
        )
        OR get_current_user_role() = 'super_admin'
    );

DROP POLICY IF EXISTS "Service role full access to template_merge_rules" ON template_merge_rules;
CREATE POLICY "Service role full access to template_merge_rules" ON template_merge_rules
    FOR ALL USING (auth.role() = 'service_role');

-- 5.9 profiles 表 RLS 策略
-- 用户可以查看和更新自己的 profile
DROP POLICY IF EXISTS "Users can view own profile" ON profiles;
CREATE POLICY "Users can view own profile" ON profiles
    FOR SELECT USING (id = auth.uid() OR get_current_user_role() = 'super_admin');

DROP POLICY IF EXISTS "Users can update own profile" ON profiles;
CREATE POLICY "Users can update own profile" ON profiles
    FOR UPDATE USING (id = auth.uid());

-- 超级管理员可以查看所有 profiles
DROP POLICY IF EXISTS "Super admin can view all profiles" ON profiles;
CREATE POLICY "Super admin can view all profiles" ON profiles
    FOR SELECT USING (get_current_user_role() = 'super_admin');

-- 租户管理员可以查看本租户的 profiles
DROP POLICY IF EXISTS "Tenant admin can view tenant profiles" ON profiles;
CREATE POLICY "Tenant admin can view tenant profiles" ON profiles
    FOR SELECT USING (
        tenant_id = get_current_user_tenant_id() 
        AND get_current_user_role() IN ('tenant_admin', 'super_admin')
    );

-- Service role 完全访问
DROP POLICY IF EXISTS "Service role full access to profiles" ON profiles;
CREATE POLICY "Service role full access to profiles" ON profiles
    FOR ALL USING (auth.role() = 'service_role');

-- ############################################################
-- PART 6: 更新 documents 表的 RLS 策略（支持多租户）
-- ############################################################

-- 删除旧策略（来自 000_init.sql）
DROP POLICY IF EXISTS "用户可以管理自己的文档" ON documents;
DROP POLICY IF EXISTS "管理员可以查看所有文档" ON documents;
DROP POLICY IF EXISTS "Service role can manage all documents" ON documents;

-- 普通用户只能查看自己的文档
DROP POLICY IF EXISTS "Users can manage own documents" ON documents;
CREATE POLICY "Users can manage own documents" ON documents
    FOR ALL USING (
        user_id = auth.uid() 
        AND (tenant_id IS NULL OR tenant_id = get_current_user_tenant_id())
    );

-- 租户管理员可以查看本租户所有文档
DROP POLICY IF EXISTS "Tenant admin can view tenant documents" ON documents;
CREATE POLICY "Tenant admin can view tenant documents" ON documents
    FOR SELECT USING (
        tenant_id = get_current_user_tenant_id() 
        AND get_current_user_role() IN ('tenant_admin', 'super_admin')
    );

-- 超级管理员可以查看所有文档
DROP POLICY IF EXISTS "Super admin can view all documents" ON documents;
CREATE POLICY "Super admin can view all documents" ON documents
    FOR ALL USING (get_current_user_role() = 'super_admin');

-- Service role 完全访问（后端 API 使用）
CREATE POLICY "Service role can manage all documents" ON documents
    FOR ALL USING (auth.role() = 'service_role');

-- ############################################################
-- PART 7: 创建自动创建 profile 的触发器
-- ############################################################

-- 当新用户注册时，自动创建 profile 记录（包含 tenant_id）
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

-- 创建触发器（仅当 auth.users 存在时）
-- 【注意】auth.users 由 GoTrue 服务启动后创建，初始化时可能不存在
-- 如果跳过，需在 auth 服务启动后执行 003_post_auth_setup.sql
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema = 'auth' AND table_name = 'users') THEN
        DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
        CREATE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users
            FOR EACH ROW EXECUTE FUNCTION handle_new_user();
        RAISE NOTICE 'auth.users 触发器创建成功';
    ELSE
        RAISE NOTICE 'auth.users 表不存在，跳过触发器创建（需在 auth 服务启动后执行 003_post_auth_setup.sql）';
    END IF;
END $$;

-- ############################################################
-- 完成
-- ############################################################

SELECT '001_multi_tenant.sql: 多租户表结构创建完成！' as message;
