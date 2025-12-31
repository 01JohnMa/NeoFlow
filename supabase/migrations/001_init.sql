-- ============================================================
-- OCR文档处理系统 - 数据库初始化脚本
-- ============================================================
-- 执行方式：通过 Supabase Studio SQL编辑器 或 psql 执行
-- ============================================================

-- 1. 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. 创建表结构

-- 文档主表
CREATE TABLE IF NOT EXISTS documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    file_name VARCHAR(500) NOT NULL,
    original_file_name VARCHAR(500),
    file_path VARCHAR(1000) NOT NULL,
    file_size BIGINT,
    file_type VARCHAR(100),
    file_extension VARCHAR(50),
    mime_type VARCHAR(100),
    document_type VARCHAR(50),
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN (
        'pending', 'uploaded', 'processing', 'completed', 'failed'
    )),
    ocr_text TEXT,
    ocr_confidence FLOAT,
    error_message TEXT,
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
    validated_by UUID REFERENCES auth.users(id),
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
    validated_by UUID REFERENCES auth.users(id),
    validated_at TIMESTAMP WITH TIME ZONE,
    validation_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT expresses_document_unique UNIQUE(document_id)
);

-- 市场抽检表
CREATE TABLE IF NOT EXISTS sampling_forms (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    inspection_result VARCHAR(64),
    product_name VARCHAR(255),
    specification_model VARCHAR(255),
    sampled_entity VARCHAR(255),
    labeled_manufacturer VARCHAR(255),
    market_regulatory_bureau VARCHAR(255),
    sampling_unit VARCHAR(255),
    sampling_date DATE,
    sampled_province VARCHAR(64),
    sampled_city VARCHAR(64),
    extraction_confidence FLOAT,
    extraction_version VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data JSONB,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_by UUID REFERENCES auth.users(id),
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

-- 3. 创建索引
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_inspection_reports_document_id ON inspection_reports(document_id);
CREATE INDEX IF NOT EXISTS idx_inspection_reports_sample_name ON inspection_reports(sample_name);
CREATE INDEX IF NOT EXISTS idx_inspection_reports_manufacturer_name ON inspection_reports(manufacturer_name);

CREATE INDEX IF NOT EXISTS idx_expresses_document_id ON expresses(document_id);
CREATE INDEX IF NOT EXISTS idx_expresses_tracking_number ON expresses(tracking_number);

CREATE INDEX IF NOT EXISTS idx_sampling_forms_document_id ON sampling_forms(document_id);
CREATE INDEX IF NOT EXISTS idx_sampling_forms_product_name ON sampling_forms(product_name);

CREATE INDEX IF NOT EXISTS idx_processing_logs_document_id ON processing_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_logs_step ON processing_logs(step);

-- 4. 创建触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE FUNCTION update_document_status()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE documents 
    SET status = 'completed',
        document_type = CASE 
            WHEN TG_TABLE_NAME = 'inspection_reports' THEN 'inspection_report'
            WHEN TG_TABLE_NAME = 'expresses' THEN 'express'
            WHEN TG_TABLE_NAME = 'sampling_forms' THEN 'sampling_form'
        END,
        processed_at = NOW()
    WHERE id = NEW.document_id;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 5. 添加触发器 (使用 IF NOT EXISTS 替代方案)
DO $$
BEGIN
    -- documents 更新时间触发器
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_documents_updated_at') THEN
        CREATE TRIGGER update_documents_updated_at 
            BEFORE UPDATE ON documents
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    -- inspection_reports 更新时间触发器
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_inspection_reports_updated_at') THEN
        CREATE TRIGGER update_inspection_reports_updated_at 
            BEFORE UPDATE ON inspection_reports
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    -- expresses 更新时间触发器
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_expresses_updated_at') THEN
        CREATE TRIGGER update_expresses_updated_at 
            BEFORE UPDATE ON expresses
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    -- sampling_forms 更新时间触发器
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_sampling_forms_updated_at') THEN
        CREATE TRIGGER update_sampling_forms_updated_at 
            BEFORE UPDATE ON sampling_forms
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    -- inspection_reports 状态更新触发器
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_doc_status_after_inspection_report') THEN
        CREATE TRIGGER update_doc_status_after_inspection_report 
            AFTER INSERT ON inspection_reports
            FOR EACH ROW EXECUTE FUNCTION update_document_status();
    END IF;

    -- expresses 状态更新触发器
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_doc_status_after_express') THEN
        CREATE TRIGGER update_doc_status_after_express 
            AFTER INSERT ON expresses
            FOR EACH ROW EXECUTE FUNCTION update_document_status();
    END IF;

    -- sampling_forms 状态更新触发器
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_doc_status_after_sampling_form') THEN
        CREATE TRIGGER update_doc_status_after_sampling_form 
            AFTER INSERT ON sampling_forms
            FOR EACH ROW EXECUTE FUNCTION update_document_status();
    END IF;
END
$$;

-- 6. 启用RLS (行级安全)
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE expresses ENABLE ROW LEVEL SECURITY;
ALTER TABLE sampling_forms ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_logs ENABLE ROW LEVEL SECURITY;

-- 7. 创建RLS策略
-- 删除已存在的策略后重新创建
DO $$
BEGIN
    -- documents 策略
    DROP POLICY IF EXISTS "用户可以管理自己的文档" ON documents;
    CREATE POLICY "用户可以管理自己的文档" ON documents
        FOR ALL USING (user_id = auth.uid());
    
    -- 允许service_role完全访问
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
END
$$;

-- 完成
SELECT '数据库初始化完成！' as message;

