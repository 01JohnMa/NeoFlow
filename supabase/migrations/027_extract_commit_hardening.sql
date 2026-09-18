-- ============================================================
-- MIGRATION 027: Extract 交卷契约补强（评审修复）
-- ============================================================
-- commit_extract_job 在成功分支补齐数据库层校验：
-- 1. 文档数量必须恰好为 1（不再直接取 document_ids[1]）
-- 2. engine 必须为空或 JSON 对象
-- 其余分支/语义与 026 完全一致（CREATE OR REPLACE，不改变已应用行为）。
-- ============================================================

CREATE OR REPLACE FUNCTION commit_extract_job(
    p_job_id UUID,
    p_worker_id TEXT,
    p_attempts INT,
    p_outcome TEXT,
    p_error TEXT,
    p_extract_data JSONB,
    p_engine JSONB
)
RETURNS TABLE (out_status TEXT, out_reason TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_job processing_jobs%ROWTYPE;
    v_document_id UUID;
BEGIN
    SELECT * INTO v_job FROM processing_jobs WHERE job_id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'not_found', 'job_unknown';
        RETURN;
    END IF;

    IF v_job.status = 'completed' AND p_outcome = 'ok' THEN
        IF EXISTS (
            SELECT 1 FROM results r
            WHERE r.job_id = p_job_id AND r.sample_key = 'extract'
        ) THEN
            RETURN QUERY SELECT 'already_committed', 'existing_artifact';
            RETURN;
        END IF;
    END IF;

    IF v_job.status <> 'processing' THEN
        RETURN QUERY SELECT 'stale', 'job_not_processing';
        RETURN;
    END IF;
    IF v_job.locked_by IS DISTINCT FROM p_worker_id
       OR v_job.attempts IS DISTINCT FROM p_attempts THEN
        RETURN QUERY SELECT 'stale_token', 'claim_ownership_lost';
        RETURN;
    END IF;

    IF p_outcome = 'ok' THEN
        -- 成功交卷要求：绑定存在且身份一致；恰好单文档；data 是对象或数组；engine 形状合法
        IF v_job.parse_result_id IS NULL THEN
            RETURN QUERY SELECT 'invalid', 'binding_missing';
            RETURN;
        END IF;
        IF v_job.document_ids IS NULL
           OR array_length(v_job.document_ids, 1) IS DISTINCT FROM 1 THEN
            RETURN QUERY SELECT 'invalid', 'document_count_invalid';
            RETURN;
        END IF;
        v_document_id := (v_job.document_ids)[1];
        PERFORM 1 FROM results r
        WHERE r.id = v_job.parse_result_id
          AND r.sample_key = 'parse'
          AND r.document_id = v_document_id
          AND r.tenant_id = v_job.tenant_id;
        IF NOT FOUND THEN
            RETURN QUERY SELECT 'invalid', 'binding_invalid';
            RETURN;
        END IF;
        IF p_extract_data IS NULL OR jsonb_typeof(p_extract_data) NOT IN ('object', 'array') THEN
            RETURN QUERY SELECT 'invalid', 'extract_data_invalid';
            RETURN;
        END IF;
        IF p_engine IS NOT NULL AND jsonb_typeof(p_engine) <> 'object' THEN
            RETURN QUERY SELECT 'invalid', 'engine_invalid';
            RETURN;
        END IF;

        INSERT INTO results (
            tenant_id, job_id, document_id, config_revision_id,
            sample_key, data, engine
        ) VALUES (
            v_job.tenant_id, p_job_id, v_document_id, v_job.configuration_revision_id,
            'extract', p_extract_data, p_engine
        )
        ON CONFLICT (job_id) WHERE sample_key = 'extract' DO NOTHING;

        UPDATE processing_jobs
        SET status = 'completed',
            stage = 'completed',
            progress = 100,
            error = NULL,
            finished_at = NOW(),
            updated_at = NOW()
        WHERE job_id = p_job_id;

        RETURN QUERY SELECT 'completed', NULL::TEXT;
        RETURN;
    ELSIF p_outcome = 'failed' THEN
        UPDATE processing_jobs
        SET status = 'failed',
            stage = 'failed',
            error = COALESCE(p_error, 'extract_failed'),
            finished_at = NOW(),
            updated_at = NOW()
        WHERE job_id = p_job_id;

        RETURN QUERY SELECT 'failed', NULL::TEXT;
        RETURN;
    END IF;

    RETURN QUERY SELECT 'invalid', 'unknown_outcome';
END;
$$;

REVOKE EXECUTE ON FUNCTION commit_extract_job(UUID, TEXT, INT, TEXT, TEXT, JSONB, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION commit_extract_job(UUID, TEXT, INT, TEXT, TEXT, JSONB, JSONB) TO service_role;

SELECT pg_notify('pgrst', 'reload schema');
SELECT '027: Extract 交卷单文档与 engine 形状校验就绪' AS message;
