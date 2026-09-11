-- ============================================================
-- 云版基础结构（Supabase Cloud 专用）
-- ============================================================
-- 用途：把 000_init.sql 中仍然需要的 documents / processing_logs
--       摘出来，跳过自建 bootstrap（角色、schema、storage 表）。
-- 执行顺序：最先执行（001_multi_tenant.sql 依赖 documents 表）。
-- ============================================================

-- 文档主表
CREATE TABLE IF NOT EXISTS documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID,  -- 无外键，通过 RLS 策略保证数据隔离
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
    source_document_ids UUID[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
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

-- 索引
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_source_document_ids ON documents USING GIN (source_document_ids);
CREATE INDEX IF NOT EXISTS idx_processing_logs_document_id ON processing_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_logs_step ON processing_logs(step);

-- 更新时间触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- RLS
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_logs ENABLE ROW LEVEL SECURITY;

-- documents 策略（001_multi_tenant.sql 会再次覆盖，保持幂等）
DROP POLICY IF EXISTS "用户可以管理自己的文档" ON documents;
CREATE POLICY "用户可以管理自己的文档" ON documents
    FOR ALL USING (user_id = auth.uid());

DROP POLICY IF EXISTS "Service role can manage all documents" ON documents;
CREATE POLICY "Service role can manage all documents" ON documents
    FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "管理员可以查看所有文档" ON documents;
CREATE POLICY "管理员可以查看所有文档" ON documents
    FOR ALL USING (
        (auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true
    );

-- processing_logs 策略
DROP POLICY IF EXISTS "用户可以查看自己文档的处理日志" ON processing_logs;
CREATE POLICY "用户可以查看自己文档的处理日志" ON processing_logs
    FOR ALL USING (
        document_id IN (SELECT id FROM documents WHERE user_id = auth.uid())
    );

DROP POLICY IF EXISTS "Service role can manage all processing_logs" ON processing_logs;
CREATE POLICY "Service role can manage all processing_logs" ON processing_logs
    FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "管理员可以查看所有处理日志" ON processing_logs;
CREATE POLICY "管理员可以查看所有处理日志" ON processing_logs
    FOR ALL USING (
        (auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true
    );

-- 表权限（云项目默认权限已覆盖，这里显式声明最小权限）
GRANT SELECT, INSERT, UPDATE, DELETE ON documents TO authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON processing_logs TO authenticated, service_role;

SELECT 'cloud/000_cloud_base.sql: documents / processing_logs 创建完成' AS message;
