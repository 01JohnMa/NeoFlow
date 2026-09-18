-- ============================================================
-- MIGRATION 026: Extract 执行契约（#32 v3.1 / ADR-0009）
-- ============================================================
-- 1. processing_jobs.parse_result_id：ParseResult 绑定（RESTRICT，防"来源被删→回退最新"）
-- 2. processing_jobs.execution_budget：跨 attempt 持久预算（请求数 + 固定 deadline）
-- 3. results.engine JSONB：执行元信息（Parse/旧行允许为空）
-- 4. results(job_id) WHERE sample_key='extract' 唯一索引
-- 5. 原子命令：ensure_extract_budget / bind_extract_parse_result /
--    consume_extract_request / commit_extract_job
-- ============================================================

ALTER TABLE processing_jobs
    ADD COLUMN IF NOT EXISTS parse_result_id UUID REFERENCES results(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS execution_budget JSONB;

ALTER TABLE results
    ADD COLUMN IF NOT EXISTS engine JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS results_extract_job_uniq
    ON results(job_id) WHERE sample_key = 'extract';

CREATE INDEX IF NOT EXISTS idx_processing_jobs_parse_result
    ON processing_jobs(parse_result_id);

-- ############ PART 1: 预算初始化（首次生效，重领不重置） ############

CREATE OR REPLACE FUNCTION ensure_extract_budget(
    p_job_id UUID,
    p_worker_id TEXT,
    p_attempts INT,
    p_max_requests INT,
    p_timeout_seconds INT
)
RETURNS TABLE (out_status TEXT, out_requests_used INT, out_max_requests INT, out_deadline TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_job processing_jobs%ROWTYPE;
BEGIN
    SELECT * INTO v_job FROM processing_jobs WHERE job_id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'not_found', NULL::INT, NULL::INT, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_job.status <> 'processing'
       OR v_job.locked_by IS DISTINCT FROM p_worker_id
       OR v_job.attempts IS DISTINCT FROM p_attempts THEN
        RETURN QUERY SELECT 'stale_token', NULL::INT, NULL::INT, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    IF v_job.execution_budget IS NULL THEN
        v_job.execution_budget := jsonb_build_object(
            'max_requests', GREATEST(p_max_requests, 1),
            'requests_used', 0,
            'deadline', (NOW() + make_interval(secs => GREATEST(p_timeout_seconds, 1)))::TEXT
        );
        UPDATE processing_jobs
        SET execution_budget = v_job.execution_budget, updated_at = NOW()
        WHERE job_id = p_job_id;
        RETURN QUERY SELECT 'initialized',
            (v_job.execution_budget->>'requests_used')::INT,
            (v_job.execution_budget->>'max_requests')::INT,
            NULLIF(v_job.execution_budget->>'deadline', '')::TIMESTAMPTZ;
        RETURN;
    END IF;

    RETURN QUERY SELECT 'existing',
        COALESCE((v_job.execution_budget->>'requests_used')::INT, 0),
        COALESCE((v_job.execution_budget->>'max_requests')::INT, 0),
        NULLIF(v_job.execution_budget->>'deadline', '')::TIMESTAMPTZ;
END;
$$;

-- ############ PART 2: 绑定（写一次 + 认领校验） ############

CREATE OR REPLACE FUNCTION bind_extract_parse_result(
    p_job_id UUID,
    p_worker_id TEXT,
    p_attempts INT,
    p_result_id UUID
)
RETURNS TABLE (out_status TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    UPDATE processing_jobs
    SET parse_result_id = p_result_id,
        stage = 'binding',
        progress = 10,
        updated_at = NOW()
    WHERE job_id = p_job_id
      AND locked_by = p_worker_id
      AND attempts = p_attempts
      AND status = 'processing'
      AND parse_result_id IS NULL;

    IF FOUND THEN
        RETURN QUERY SELECT 'bound';
        RETURN;
    END IF;

    RETURN QUERY SELECT 'rejected';
END;
$$;

-- ############ PART 3: 请求预算消费（认领保护、跨 attempt 累计） ############

CREATE OR REPLACE FUNCTION consume_extract_request(
    p_job_id UUID,
    p_worker_id TEXT,
    p_attempts INT
)
RETURNS TABLE (out_allowed BOOLEAN, out_reason TEXT, out_requests_used INT, out_max_requests INT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_job processing_jobs%ROWTYPE;
    v_used INT;
    v_max INT;
    v_deadline TIMESTAMPTZ;
BEGIN
    SELECT * INTO v_job FROM processing_jobs WHERE job_id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'job_unknown', NULL::INT, NULL::INT;
        RETURN;
    END IF;
    IF v_job.status <> 'processing'
       OR v_job.locked_by IS DISTINCT FROM p_worker_id
       OR v_job.attempts IS DISTINCT FROM p_attempts THEN
        RETURN QUERY SELECT FALSE, 'stale_token', NULL::INT, NULL::INT;
        RETURN;
    END IF;

    v_used := COALESCE((v_job.execution_budget->>'requests_used')::INT, 0);
    v_max := COALESCE((v_job.execution_budget->>'max_requests')::INT, 0);
    v_deadline := NULLIF(v_job.execution_budget->>'deadline', '')::TIMESTAMPTZ;

    IF v_max <= 0 OR v_deadline IS NULL THEN
        RETURN QUERY SELECT FALSE, 'budget_uninitialized', v_used, v_max;
        RETURN;
    END IF;
    IF NOW() > v_deadline THEN
        RETURN QUERY SELECT FALSE, 'deadline_exceeded', v_used, v_max;
        RETURN;
    END IF;
    IF v_used >= v_max THEN
        RETURN QUERY SELECT FALSE, 'requests_exhausted', v_used, v_max;
        RETURN;
    END IF;

    v_used := v_used + 1;
    UPDATE processing_jobs
    SET execution_budget = jsonb_set(v_job.execution_budget, '{requests_used}', to_jsonb(v_used)),
        updated_at = NOW()
    WHERE job_id = p_job_id;

    RETURN QUERY SELECT TRUE, NULL::TEXT, v_used, v_max;
END;
$$;

-- ############ PART 4: 原子交卷 ############

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
        -- 成功交卷要求：绑定存在且身份一致；data 必须是对象或数组
        IF v_job.parse_result_id IS NULL THEN
            RETURN QUERY SELECT 'invalid', 'binding_missing';
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

-- ############ PART 5: 权限（仅 service_role） ############

REVOKE EXECUTE ON FUNCTION ensure_extract_budget(UUID, TEXT, INT, INT, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION ensure_extract_budget(UUID, TEXT, INT, INT, INT) TO service_role;

REVOKE EXECUTE ON FUNCTION bind_extract_parse_result(UUID, TEXT, INT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION bind_extract_parse_result(UUID, TEXT, INT, UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION consume_extract_request(UUID, TEXT, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION consume_extract_request(UUID, TEXT, INT) TO service_role;

REVOKE EXECUTE ON FUNCTION commit_extract_job(UUID, TEXT, INT, TEXT, TEXT, JSONB, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION commit_extract_job(UUID, TEXT, INT, TEXT, TEXT, JSONB, JSONB) TO service_role;

SELECT pg_notify('pgrst', 'reload schema');
SELECT '026: Extract 执行契约（绑定/预算/交卷）就绪' AS message;
