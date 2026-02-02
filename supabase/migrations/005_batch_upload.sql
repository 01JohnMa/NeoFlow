-- ============================================================
-- 批量上传功能 - 数据库迁移脚本
-- ============================================================
-- 功能：支持批量上传文档并追踪处理进度
-- 包含：批次表、文档表扩展字段、索引、RLS策略
-- ============================================================

-- ############################################################
-- PART 1: 创建批次表 (document_batches)
-- ############################################################

CREATE TABLE IF NOT EXISTS document_batches (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    tenant_id UUID REFERENCES tenants(id),
    -- 批次模式：single=质量运营独立处理, merge=照明配对合并
    batch_mode VARCHAR(20) DEFAULT 'single' CHECK (batch_mode IN ('single', 'merge')),
    -- 对于 merge 模式，total_count 是组数而非文件数
    total_count INT NOT NULL DEFAULT 0,
    completed_count INT NOT NULL DEFAULT 0,
    failed_count INT NOT NULL DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN (
        'pending', 'processing', 'completed', 'partial_failed', 'interrupted'
    )),
    -- 批次级错误信息
    error_message TEXT,
    -- 扩展字段（存储批次额外配置或统计信息）
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- ############################################################
-- PART 2: 扩展 documents 表，添加批次关联字段
-- ############################################################

-- 添加批次关联字段
ALTER TABLE documents ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES document_batches(id);

-- 添加组号字段（用于 merge 模式，标识属于哪一组）
ALTER TABLE documents ADD COLUMN IF NOT EXISTS batch_group_index INT;

-- 添加原始文档ID关联字段（合并模式时记录源文件ID）
-- 注意：PostgreSQL 不支持数组的外键约束，使用 JSONB 或 UUID[] 存储
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_document_ids UUID[];

-- ############################################################
-- PART 3: 创建索引
-- ############################################################

-- 批次表索引
CREATE INDEX IF NOT EXISTS idx_batches_user_id ON document_batches(user_id);
CREATE INDEX IF NOT EXISTS idx_batches_tenant_id ON document_batches(tenant_id);
CREATE INDEX IF NOT EXISTS idx_batches_status ON document_batches(status);
CREATE INDEX IF NOT EXISTS idx_batches_user_status ON document_batches(user_id, status);
CREATE INDEX IF NOT EXISTS idx_batches_tenant_created ON document_batches(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_batches_batch_mode ON document_batches(batch_mode);

-- 文档表批次相关索引
CREATE INDEX IF NOT EXISTS idx_documents_batch_id ON documents(batch_id);
CREATE INDEX IF NOT EXISTS idx_documents_batch_group ON documents(batch_id, batch_group_index);

-- ############################################################
-- PART 4: 创建触发器（自动更新 updated_at）
-- ############################################################

DROP TRIGGER IF EXISTS update_document_batches_updated_at ON document_batches;
CREATE TRIGGER update_document_batches_updated_at 
    BEFORE UPDATE ON document_batches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ############################################################
-- PART 5: 启用 RLS 并创建策略
-- ############################################################

-- 启用 RLS
ALTER TABLE document_batches ENABLE ROW LEVEL SECURITY;

-- 用户可以查看和管理自己的批次
DROP POLICY IF EXISTS "Users can manage own batches" ON document_batches;
CREATE POLICY "Users can manage own batches" ON document_batches
    FOR ALL USING (
        user_id = auth.uid()
        OR tenant_id = get_current_user_tenant_id()
    );

-- 租户管理员可以查看本租户所有批次
DROP POLICY IF EXISTS "Tenant admin can view tenant batches" ON document_batches;
CREATE POLICY "Tenant admin can view tenant batches" ON document_batches
    FOR SELECT USING (
        tenant_id = get_current_user_tenant_id() 
        AND get_current_user_role() IN ('tenant_admin', 'super_admin')
    );

-- 超级管理员可以查看所有批次
DROP POLICY IF EXISTS "Super admin can view all batches" ON document_batches;
CREATE POLICY "Super admin can view all batches" ON document_batches
    FOR ALL USING (get_current_user_role() = 'super_admin');

-- Service role 完全访问（后端 API 使用）
DROP POLICY IF EXISTS "Service role full access to batches" ON document_batches;
CREATE POLICY "Service role full access to batches" ON document_batches
    FOR ALL USING (auth.role() = 'service_role');

-- ############################################################
-- 完成
-- ############################################################

SELECT '005_batch_upload.sql: 批量上传表结构创建完成！' as message;
