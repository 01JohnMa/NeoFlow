-- ============================================================
-- MIGRATION 012: 新增 processing_jobs 与 feishu_push_records
-- ============================================================

ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_status_check;

ALTER TABLE documents
    ADD CONSTRAINT documents_status_check CHECK (status IN (
        'pending', 'uploaded', 'queued', 'processing', 'pending_review', 'completed', 'failed'
    ));

CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    job_type VARCHAR(50) NOT NULL DEFAULT 'batch',
    status VARCHAR(50) NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'pending', 'processing', 'completed', 'failed'
    )),
    stage VARCHAR(50) NOT NULL DEFAULT 'queued',
    progress INT NOT NULL DEFAULT 0,
    document_ids UUID[] DEFAULT ARRAY[]::UUID[],
    items JSONB DEFAULT '[]'::jsonb,
    total INT NOT NULL DEFAULT 0,
    completed_count INT NOT NULL DEFAULT 0,
    error TEXT,
    created_by UUID,
    dedupe_key TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_status_created_at
    ON processing_jobs(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_dedupe_key
    ON processing_jobs(dedupe_key);

CREATE TABLE IF NOT EXISTS feishu_push_records (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    document_id TEXT NOT NULL,
    template_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feishu_push_records_document_id
    ON feishu_push_records(document_id, created_at DESC);

SELECT pg_notify('pgrst', 'reload schema');
SELECT '012: processing_jobs 与 feishu_push_records 创建完成' AS message;
