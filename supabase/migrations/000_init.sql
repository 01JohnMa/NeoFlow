-- ============================================================
-- Supabase 完整初始化脚本
-- ============================================================
-- 【重要】此文件由 docker-entrypoint-initdb.d 自动执行
-- 包含：角色、Schema、Storage表、应用表、RLS策略
-- 部署方式：docker-compose up -d 一条命令完成所有初始化
-- ============================================================

-- ############################################################
-- PART 1: 角色和 Schema 初始化
-- ############################################################

-- 1.1 创建必要的角色
DO $$
BEGIN
    -- 创建 anon 角色
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN NOINHERIT;
    END IF;

    -- 创建 authenticated 角色
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN NOINHERIT;
    END IF;

    -- 创建 service_role 角色
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
    END IF;

    -- 创建 supabase_auth_admin 用户
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supabase_auth_admin') THEN
        CREATE ROLE supabase_auth_admin LOGIN CREATEROLE CREATEDB REPLICATION BYPASSRLS;
    END IF;

    -- 创建 supabase_storage_admin 用户
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supabase_storage_admin') THEN
        CREATE ROLE supabase_storage_admin LOGIN CREATEROLE CREATEDB REPLICATION BYPASSRLS;
    END IF;

    -- 创建 authenticator 用户
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'authenticator') THEN
        CREATE ROLE authenticator LOGIN NOINHERIT;
    END IF;

    -- 创建 supabase_admin 用户
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supabase_admin') THEN
        CREATE ROLE supabase_admin LOGIN CREATEROLE CREATEDB REPLICATION BYPASSRLS;
    END IF;
END
$$;

-- ============================================================
-- 【生产环境警告】以下密码仅供开发测试使用！
-- 部署到生产环境前，必须修改为强密码或使用环境变量
-- 建议：使用 openssl rand -base64 32 生成随机密码
-- ============================================================
ALTER ROLE supabase_auth_admin WITH PASSWORD '123456';
ALTER ROLE supabase_storage_admin WITH PASSWORD '123456';
ALTER ROLE authenticator WITH PASSWORD '123456';
ALTER ROLE supabase_admin WITH PASSWORD '123456';

-- 1.2 【关键】设置 search_path，GoTrue 查询时不带 schema 前缀
ALTER ROLE supabase_auth_admin SET search_path TO auth, public, extensions;
ALTER ROLE supabase_storage_admin SET search_path TO storage, public, extensions;

-- 1.3 【关键】先创建 schema，再授予权限
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS storage;
CREATE SCHEMA IF NOT EXISTS extensions;

-- 1.4 授予 schema 权限
GRANT ALL ON SCHEMA public TO supabase_auth_admin, supabase_storage_admin, supabase_admin, postgres;
GRANT ALL ON SCHEMA auth TO supabase_auth_admin, supabase_storage_admin, supabase_admin, postgres;
GRANT ALL ON SCHEMA storage TO supabase_auth_admin, supabase_storage_admin, supabase_admin, postgres;
GRANT ALL ON SCHEMA extensions TO supabase_auth_admin, supabase_storage_admin, supabase_admin, postgres;
GRANT ALL ON SCHEMA public TO authenticator;

-- 1.5 授予角色权限
GRANT anon TO authenticator;
GRANT authenticated TO authenticator;
GRANT service_role TO authenticator;

-- 1.6 授予数据库权限
GRANT ALL ON DATABASE postgres TO supabase_auth_admin;
GRANT ALL ON DATABASE postgres TO supabase_storage_admin;
GRANT ALL ON DATABASE postgres TO supabase_admin;
GRANT ALL ON DATABASE postgres TO postgres;

-- 确保超级用户权限和 RLS 绕过
ALTER ROLE supabase_admin BYPASSRLS;
ALTER ROLE postgres BYPASSRLS;

-- 1.7 授予 schema 所有权限
GRANT ALL ON SCHEMA auth TO supabase_auth_admin;
GRANT ALL ON SCHEMA storage TO supabase_storage_admin;
GRANT ALL ON SCHEMA auth TO supabase_admin;
GRANT ALL ON SCHEMA storage TO supabase_admin;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

-- 授予现有对象的权限
GRANT ALL ON ALL TABLES IN SCHEMA auth TO supabase_admin, postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA auth TO supabase_admin, postgres;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA auth TO supabase_admin, postgres;

GRANT ALL ON ALL TABLES IN SCHEMA storage TO supabase_admin, postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA storage TO supabase_admin, postgres;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA storage TO supabase_admin, postgres;

GRANT ALL ON ALL TABLES IN SCHEMA public TO supabase_admin, postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO supabase_admin, postgres;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO supabase_admin, postgres;

-- 1.8 设置默认权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO supabase_auth_admin, supabase_storage_admin, supabase_admin, postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO supabase_auth_admin, supabase_storage_admin, supabase_admin, postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO supabase_auth_admin, supabase_storage_admin, supabase_admin, postgres;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT ALL ON TABLES TO supabase_admin, postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT ALL ON SEQUENCES TO supabase_admin, postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT ALL ON FUNCTIONS TO supabase_admin, postgres;

ALTER DEFAULT PRIVILEGES IN SCHEMA storage GRANT ALL ON TABLES TO supabase_admin, postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA storage GRANT ALL ON SEQUENCES TO supabase_admin, postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA storage GRANT ALL ON FUNCTIONS TO supabase_admin, postgres;

-- ############################################################
-- PART 2: DEFAULT PRIVILEGES 预设（解决 Studio 权限问题）
-- ############################################################
-- 【关键】当 supabase_auth_admin 创建 auth.users 等表时，
-- supabase_admin 自动获得访问权限，使 Studio 可以看到用户表
-- ============================================================

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_auth_admin IN SCHEMA auth 
    GRANT ALL ON TABLES TO supabase_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_auth_admin IN SCHEMA auth 
    GRANT ALL ON SEQUENCES TO supabase_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_auth_admin IN SCHEMA auth 
    GRANT ALL ON FUNCTIONS TO supabase_admin;

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_storage_admin IN SCHEMA storage 
    GRANT ALL ON TABLES TO supabase_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_storage_admin IN SCHEMA storage 
    GRANT ALL ON SEQUENCES TO supabase_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_storage_admin IN SCHEMA storage 
    GRANT ALL ON FUNCTIONS TO supabase_admin;

SELECT 'PART 1-2: 角色和权限初始化完成！' as message;

-- ############################################################
-- PART 3: Storage 基础表和 RLS 策略
-- ############################################################

-- 3.1 创建 buckets 表
CREATE TABLE IF NOT EXISTS storage.buckets (
    id text NOT NULL PRIMARY KEY,
    name text NOT NULL UNIQUE,
    owner uuid,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    public boolean DEFAULT false,
    avif_autodetection boolean DEFAULT false,
    file_size_limit bigint,
    allowed_mime_types text[]
);

-- 3.2 创建 objects 表
CREATE TABLE IF NOT EXISTS storage.objects (
    id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    bucket_id text REFERENCES storage.buckets(id),
    name text,
    owner uuid,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    last_accessed_at timestamptz DEFAULT now(),
    metadata jsonb,
    path_tokens text[] GENERATED ALWAYS AS (string_to_array(name, '/')) STORED,
    version text,
    UNIQUE (bucket_id, name)
);

-- 3.3 创建索引
CREATE INDEX IF NOT EXISTS bname ON storage.buckets USING btree (name);
CREATE INDEX IF NOT EXISTS bucketid_objname ON storage.objects USING btree (bucket_id, name);
CREATE INDEX IF NOT EXISTS name_prefix_search ON storage.objects USING btree (name text_pattern_ops);

-- 3.4 设置 RLS
ALTER TABLE storage.buckets ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

-- 3.5 转移所有权
ALTER TABLE storage.buckets OWNER TO supabase_storage_admin;
ALTER TABLE storage.objects OWNER TO supabase_storage_admin;

-- 3.6 授权
GRANT ALL ON storage.buckets TO authenticated, service_role;
GRANT ALL ON storage.objects TO authenticated, service_role;
GRANT SELECT ON storage.buckets TO anon;
GRANT SELECT ON storage.objects TO anon;

-- 3.7 Storage RLS 策略
-- 允许 service_role 完全访问
DROP POLICY IF EXISTS "Service role full access to buckets" ON storage.buckets;
CREATE POLICY "Service role full access to buckets" ON storage.buckets
    FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "Service role full access to objects" ON storage.objects;
CREATE POLICY "Service role full access to objects" ON storage.objects
    FOR ALL USING (auth.role() = 'service_role');

-- 允许用户访问公开 bucket
DROP POLICY IF EXISTS "Public buckets are visible to all" ON storage.buckets;
CREATE POLICY "Public buckets are visible to all" ON storage.buckets
    FOR SELECT USING (public = true);

DROP POLICY IF EXISTS "Public objects are visible to all" ON storage.objects;
CREATE POLICY "Public objects are visible to all" ON storage.objects
    FOR SELECT USING (bucket_id IN (SELECT id FROM storage.buckets WHERE public = true));

-- 允许认证用户访问自己的文件
DROP POLICY IF EXISTS "Users can manage own objects" ON storage.objects;
CREATE POLICY "Users can manage own objects" ON storage.objects
    FOR ALL USING (auth.uid() = owner);

SELECT 'PART 3: Storage 基础表和 RLS 策略创建完成！' as message;

-- ############################################################
-- PART 4: OCR 应用表（无外键约束，通过 RLS 保证数据隔离）
-- ############################################################
-- 【重要】移除了对 auth.users 的外键引用
-- 原因：auth.users 由 auth 服务动态创建，初始化时尚不存在
-- 数据隔离通过 RLS 策略 user_id = auth.uid() 保证
-- ============================================================

-- 4.1 创建业务表

-- 文档主表
CREATE TABLE IF NOT EXISTS documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID,  -- 移除外键约束，通过 RLS 策略保证数据隔离
    file_name VARCHAR(500) NOT NULL,
    original_file_name VARCHAR(500),
    display_name VARCHAR(255),
    file_path VARCHAR(1000) NOT NULL,
    file_size BIGINT,
    file_type VARCHAR(100),
    file_extension VARCHAR(50),
    mime_type VARCHAR(100),
    document_type VARCHAR(50),
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN (
        'pending', 'uploaded', 'processing', 'pending_review', 'completed', 'failed'
    )),
    ocr_text TEXT,
    ocr_confidence FLOAT,
    error_message TEXT,
    source_document_ids UUID[],  -- 合并文档关联的原始文档ID列表
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

-- 检验报告表
CREATE TABLE IF NOT EXISTS inspection_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    sample_name VARCHAR(255),
    specification_model VARCHAR(255),
    production_date_batch VARCHAR(255),
    inspected_unit_name VARCHAR(255),
    inspected_unit_address VARCHAR(512),
    inspected_unit_phone VARCHAR(64),
    manufacturer_name VARCHAR(255),
    manufacturer_address VARCHAR(512),
    manufacturer_phone VARCHAR(64),
    task_source VARCHAR(255),
    sampling_agency VARCHAR(255),
    sampling_date DATE,
    inspection_conclusion VARCHAR(255),
    inspection_category VARCHAR(255),
    notes TEXT,
    inspector VARCHAR(64),
    reviewer VARCHAR(64),
    approver VARCHAR(64),
    extraction_confidence FLOAT,
    extraction_version VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data JSONB,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_by UUID,  -- 移除外键约束
    validated_at TIMESTAMP WITH TIME ZONE,
    validation_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT inspection_reports_document_unique UNIQUE(document_id)
);

-- 快递面单表
CREATE TABLE IF NOT EXISTS expresses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    tracking_number VARCHAR(64),
    recipient VARCHAR(128),
    delivery_address TEXT,
    sender VARCHAR(128),
    sender_address TEXT,
    notes TEXT,
    extraction_confidence FLOAT,
    extraction_version VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data JSONB,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_by UUID,  -- 移除外键约束
    validated_at TIMESTAMP WITH TIME ZONE,
    validation_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT expresses_document_unique UNIQUE(document_id)
);

-- 抽样单表
CREATE TABLE IF NOT EXISTS sampling_forms (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    task_source VARCHAR(255),
    task_category VARCHAR(64),
    manufacturer VARCHAR(255),
    sample_name VARCHAR(255),
    specification_model VARCHAR(255),
    production_date_batch VARCHAR(100),
    sample_storage_location VARCHAR(255),
    sampling_channel VARCHAR(100),
    sampling_unit VARCHAR(255),
    sampling_date DATE,
    sampled_province VARCHAR(64),
    sampled_city VARCHAR(64),
    extraction_confidence FLOAT,
    extraction_version VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data JSONB,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_by UUID,  -- 移除外键约束
    validated_at TIMESTAMP WITH TIME ZONE,
    validation_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT sampling_forms_document_unique UNIQUE(document_id)
);

-- 处理日志表
CREATE TABLE IF NOT EXISTS processing_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    step VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    message TEXT,
    error_details TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4.2 创建索引
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_source_document_ids ON documents USING GIN (source_document_ids);

CREATE INDEX IF NOT EXISTS idx_inspection_reports_document_id ON inspection_reports(document_id);
CREATE INDEX IF NOT EXISTS idx_inspection_reports_sample_name ON inspection_reports(sample_name);
CREATE INDEX IF NOT EXISTS idx_inspection_reports_manufacturer_name ON inspection_reports(manufacturer_name);

CREATE INDEX IF NOT EXISTS idx_expresses_document_id ON expresses(document_id);
CREATE INDEX IF NOT EXISTS idx_expresses_tracking_number ON expresses(tracking_number);

CREATE INDEX IF NOT EXISTS idx_sampling_forms_document_id ON sampling_forms(document_id);
CREATE INDEX IF NOT EXISTS idx_sampling_forms_sample_name ON sampling_forms(sample_name);

CREATE INDEX IF NOT EXISTS idx_processing_logs_document_id ON processing_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_logs_step ON processing_logs(step);

-- 4.3 创建触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 4.4 创建更新时间触发器
DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at 
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_inspection_reports_updated_at ON inspection_reports;
CREATE TRIGGER update_inspection_reports_updated_at 
    BEFORE UPDATE ON inspection_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_expresses_updated_at ON expresses;
CREATE TRIGGER update_expresses_updated_at 
    BEFORE UPDATE ON expresses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_sampling_forms_updated_at ON sampling_forms;
CREATE TRIGGER update_sampling_forms_updated_at 
    BEFORE UPDATE ON sampling_forms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 4.5 启用 RLS
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE expresses ENABLE ROW LEVEL SECURITY;
ALTER TABLE sampling_forms ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_logs ENABLE ROW LEVEL SECURITY;

-- 4.6 创建 RLS 策略（保证用户数据隔离）

-- documents 策略
DROP POLICY IF EXISTS "用户可以管理自己的文档" ON documents;
CREATE POLICY "用户可以管理自己的文档" ON documents
    FOR ALL USING (user_id = auth.uid());

DROP POLICY IF EXISTS "Service role can manage all documents" ON documents;
CREATE POLICY "Service role can manage all documents" ON documents
    FOR ALL USING (auth.role() = 'service_role');

-- inspection_reports 策略
DROP POLICY IF EXISTS "用户可以查看自己文档的检验报告" ON inspection_reports;
CREATE POLICY "用户可以查看自己文档的检验报告" ON inspection_reports
    FOR ALL USING (
        document_id IN (SELECT id FROM documents WHERE user_id = auth.uid())
    );

DROP POLICY IF EXISTS "Service role can manage all inspection_reports" ON inspection_reports;
CREATE POLICY "Service role can manage all inspection_reports" ON inspection_reports
    FOR ALL USING (auth.role() = 'service_role');

-- expresses 策略
DROP POLICY IF EXISTS "用户可以查看自己文档的快递面单" ON expresses;
CREATE POLICY "用户可以查看自己文档的快递面单" ON expresses
    FOR ALL USING (
        document_id IN (SELECT id FROM documents WHERE user_id = auth.uid())
    );

DROP POLICY IF EXISTS "Service role can manage all expresses" ON expresses;
CREATE POLICY "Service role can manage all expresses" ON expresses
    FOR ALL USING (auth.role() = 'service_role');

-- sampling_forms 策略
DROP POLICY IF EXISTS "用户可以查看自己文档的市场抽检表" ON sampling_forms;
CREATE POLICY "用户可以查看自己文档的市场抽检表" ON sampling_forms
    FOR ALL USING (
        document_id IN (SELECT id FROM documents WHERE user_id = auth.uid())
    );

DROP POLICY IF EXISTS "Service role can manage all sampling_forms" ON sampling_forms;
CREATE POLICY "Service role can manage all sampling_forms" ON sampling_forms
    FOR ALL USING (auth.role() = 'service_role');

-- processing_logs 策略
DROP POLICY IF EXISTS "用户可以查看自己文档的处理日志" ON processing_logs;
CREATE POLICY "用户可以查看自己文档的处理日志" ON processing_logs
    FOR ALL USING (
        document_id IN (SELECT id FROM documents WHERE user_id = auth.uid())
    );

DROP POLICY IF EXISTS "Service role can manage all processing_logs" ON processing_logs;
CREATE POLICY "Service role can manage all processing_logs" ON processing_logs
    FOR ALL USING (auth.role() = 'service_role');

SELECT 'PART 4: OCR 应用表创建完成！' as message;

-- ############################################################
-- PART 5: 管理员 RLS 策略
-- ############################################################
-- 允许 app_metadata 中有 is_admin=true 的用户查看所有文档
-- ============================================================

-- documents 表管理员策略
DROP POLICY IF EXISTS "管理员可以查看所有文档" ON documents;
CREATE POLICY "管理员可以查看所有文档" ON documents
    FOR ALL USING (
        (auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true
    );

-- inspection_reports 表管理员策略
DROP POLICY IF EXISTS "管理员可以查看所有检验报告" ON inspection_reports;
CREATE POLICY "管理员可以查看所有检验报告" ON inspection_reports
    FOR ALL USING (
        (auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true
    );

-- expresses 表管理员策略
DROP POLICY IF EXISTS "管理员可以查看所有快递单" ON expresses;
CREATE POLICY "管理员可以查看所有快递单" ON expresses
    FOR ALL USING (
        (auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true
    );

-- sampling_forms 表管理员策略
DROP POLICY IF EXISTS "管理员可以查看所有抽样单" ON sampling_forms;
CREATE POLICY "管理员可以查看所有抽样单" ON sampling_forms
    FOR ALL USING (
        (auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true
    );

-- processing_logs 表管理员策略
DROP POLICY IF EXISTS "管理员可以查看所有处理日志" ON processing_logs;
CREATE POLICY "管理员可以查看所有处理日志" ON processing_logs
    FOR ALL USING (
        (auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true
    );

SELECT 'PART 5: 管理员 RLS 策略创建完成！' as message;

-- ############################################################
-- 初始化完成
-- ############################################################

SELECT '========================================' as separator;
SELECT '000_init.sql: 数据库初始化完成！' as message;
SELECT '========================================' as separator;

-- ============================================================
-- 【如果 Studio 看不到 auth.users 表】
-- ============================================================
-- DEFAULT PRIVILEGES 对新创建的表生效，但如果仍有问题，
-- 在所有服务启动后执行以下命令：
-- 
-- docker exec -i supabase-db psql -U postgres -d postgres -c \
--   "GRANT ALL ON ALL TABLES IN SCHEMA auth TO supabase_admin; \
--    GRANT ALL ON ALL SEQUENCES IN SCHEMA auth TO supabase_admin; \
--    GRANT USAGE ON SCHEMA auth TO supabase_admin;"
-- ============================================================

-- ============================================================
-- 设置管理员用户（手动执行，auth 服务启动后）
-- ============================================================
-- 将某个用户设置为管理员：
-- UPDATE auth.users 
-- SET raw_app_meta_data = jsonb_set(
--     COALESCE(raw_app_meta_data, '{}'::jsonb), 
--     '{is_admin}', 
--     'true'
-- ) 
-- WHERE email = 'admin@example.com';
-- ============================================================

-- ############################################################
-- PART 6: 照明综合报告表 (lighting_reports)
-- ############################################################

CREATE TABLE IF NOT EXISTS lighting_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    
    -- 来自积分球（14个字段）
    sample_model VARCHAR(255),              -- 样品型号
    chromaticity_x VARCHAR(64),             -- 色品坐标X
    chromaticity_y VARCHAR(64),             -- 色品坐标Y
    duv VARCHAR(64),                        -- duv
    cct VARCHAR(64),                        -- 色温(CCT)
    ra VARCHAR(64),                         -- Ra
    r9 VARCHAR(64),                         -- R9
    cqs VARCHAR(64),                        -- CQS
    sdcm VARCHAR(64),                       -- 色容差SDCM
    power_sphere VARCHAR(64),               -- 功率(积分球)
    luminous_flux_sphere VARCHAR(64),       -- 光通量(积分球)
    luminous_efficacy_sphere VARCHAR(64),   -- 光效(积分球)
    rf VARCHAR(64),                         -- Rf
    rg VARCHAR(64),                         -- Rg
    
    -- 来自光分布（6个字段）
    lamp_specification VARCHAR(255),        -- 灯具规格
    power VARCHAR(64),                      -- 功率
    luminous_flux VARCHAR(64),              -- 光通量(光分布)
    luminous_efficacy VARCHAR(64),          -- 光效(光分布)
    peak_intensity VARCHAR(64),             -- 峰值光强
    beam_angle VARCHAR(64),                 -- 光束角
    
    -- 元数据
    extraction_confidence FLOAT,
    extraction_version VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data JSONB,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_by UUID,
    validated_at TIMESTAMP WITH TIME ZONE,
    validation_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT lighting_reports_document_unique UNIQUE(document_id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_lighting_reports_document_id ON lighting_reports(document_id);
CREATE INDEX IF NOT EXISTS idx_lighting_reports_sample_model ON lighting_reports(sample_model);

-- 创建更新时间触发器
DROP TRIGGER IF EXISTS update_lighting_reports_updated_at ON lighting_reports;
CREATE TRIGGER update_lighting_reports_updated_at 
    BEFORE UPDATE ON lighting_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 启用 RLS
ALTER TABLE lighting_reports ENABLE ROW LEVEL SECURITY;

-- RLS 策略：用户可以查看自己文档的照明报告
DROP POLICY IF EXISTS "用户可以查看自己文档的照明报告" ON lighting_reports;
CREATE POLICY "用户可以查看自己文档的照明报告" ON lighting_reports
    FOR ALL USING (
        document_id IN (SELECT id FROM documents WHERE user_id = auth.uid())
    );

-- RLS 策略：Service role 完全访问
DROP POLICY IF EXISTS "Service role can manage all lighting_reports" ON lighting_reports;
CREATE POLICY "Service role can manage all lighting_reports" ON lighting_reports
    FOR ALL USING (auth.role() = 'service_role');

-- RLS 策略：管理员可以查看所有照明报告
DROP POLICY IF EXISTS "管理员可以查看所有照明报告" ON lighting_reports;
CREATE POLICY "管理员可以查看所有照明报告" ON lighting_reports
    FOR ALL USING (
        (auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true
    );

SELECT 'PART 6: 照明综合报告表创建完成！' as message;
