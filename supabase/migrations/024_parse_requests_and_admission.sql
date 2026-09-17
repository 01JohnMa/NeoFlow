-- ============================================================
-- MIGRATION 024: Parse 受理记录、执行规格与原子命令
-- ============================================================
-- 背景（ADR-0007/0008，issue #30 v3.2）：
--   * Parse 是参数化能力：每个 Job 只解析一个 Document，参数记录在
--     processing_jobs.execution_spec，不再固定 Configuration Revision；
--   * 一次提交 = 原子受理 N 个单文件 Job + 一条 job_requests 记录；
--   * 受理/交卷/删除三个动作必须各自在一个数据库事务内完成。
--
-- 本迁移新增：
--   1. job_requests（受理台账：幂等键、请求指纹、策略版本）
--   2. processing_jobs.execution_spec / request_id
--   3. results(job_id) 在 sample_key='parse' 上的规范产物唯一索引
--   4. admit_parse_request / commit_parse_job / delete_document_guarded
--   5. RLS 与函数执行权限（仅 service_role）
--
-- 无数据回填：历史 Job 保持 legacy（execution_spec 为 NULL）。
-- ============================================================

-- ############################################################
-- PART 1: job_requests（受理台账）
-- ############################################################

CREATE TABLE IF NOT EXISTS job_requests (
    request_id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id               UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    requester_id            UUID NOT NULL,
    capability              VARCHAR(50) NOT NULL CHECK (capability IN ('parse')),
    idempotency_key         TEXT,
    request_fingerprint     TEXT NOT NULL,
    request_payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_version          TEXT NOT NULL,
    reused_from_request_id  UUID REFERENCES job_requests(request_id) ON DELETE SET NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE job_requests IS
    '能力受理台账：一次提交一条；幂等键与请求指纹用于重试判定，Job 通过 request_id 归属到请求';

CREATE UNIQUE INDEX IF NOT EXISTS uq_job_requests_idempotency
    ON job_requests(tenant_id, requester_id, capability, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_job_requests_tenant_created_at
    ON job_requests(tenant_id, created_at DESC);

ALTER TABLE job_requests ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON job_requests FROM anon, authenticated;
GRANT ALL ON job_requests TO service_role;

DROP POLICY IF EXISTS "Service role full access to job_requests" ON job_requests;
CREATE POLICY "Service role full access to job_requests" ON job_requests
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ############################################################
-- PART 2: processing_jobs 执行规格与请求归属
-- ############################################################

ALTER TABLE processing_jobs
    ADD COLUMN IF NOT EXISTS execution_spec JSONB,
    ADD COLUMN IF NOT EXISTS request_id UUID REFERENCES job_requests(request_id) ON DELETE SET NULL;

COMMENT ON COLUMN processing_jobs.execution_spec IS
    '不可变执行规格（参数化能力）：capability/spec_version/document_id/input_selection/effective_params/policy_version；历史 Job 为 NULL';
COMMENT ON COLUMN processing_jobs.request_id IS
    '受理台账引用：本次 Job 由哪次提交创建；历史 Job 为 NULL';

CREATE INDEX IF NOT EXISTS idx_processing_jobs_request_id
    ON processing_jobs(request_id);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_tenant_status
    ON processing_jobs(tenant_id, status);

-- ############################################################
-- PART 3: 规范产物唯一性（同一 Job 的 parse 结果只能有一条）
-- ############################################################

CREATE UNIQUE INDEX IF NOT EXISTS uq_results_parse_job
    ON results(job_id)
    WHERE sample_key = 'parse';

-- ############################################################
-- PART 4: 原子命令 —— 受理
-- ############################################################

CREATE OR REPLACE FUNCTION admit_parse_request(
    p_tenant_id UUID,
    p_requester_id UUID,
    p_is_admin BOOLEAN,
    p_document_ids UUID[],
    p_spec JSONB,
    p_idempotency_key TEXT,
    p_request_fingerprint TEXT,
    p_policy_version TEXT,
    p_max_files INT,
    p_max_active_jobs INT
)
RETURNS TABLE (
    out_status TEXT,
    out_request_id UUID,
    out_job_ids UUID[],
    out_reason TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_doc_total INT;
    v_doc_count INT;
    v_request_id UUID;
    v_source_request_id UUID;
    v_existing_fingerprint TEXT;
    v_existing_reused_from UUID;
    v_conflict RECORD;
    v_active_count INT;
    v_job_ids UUID[] := '{}';
    v_new_job_id UUID;
    v_doc_id UUID;
BEGIN
    -- 0. 纵深防御（API 层已完成格式校验）
    IF p_document_ids IS NULL OR cardinality(p_document_ids) = 0 THEN
        RETURN QUERY SELECT 'invalid', NULL::UUID, NULL::UUID[], 'document_ids_empty';
        RETURN;
    END IF;
    v_doc_total := cardinality(p_document_ids);
    IF (SELECT count(DISTINCT x) FROM unnest(p_document_ids) AS x) <> v_doc_total THEN
        RETURN QUERY SELECT 'invalid', NULL::UUID, NULL::UUID[], 'document_ids_duplicated';
        RETURN;
    END IF;
    IF v_doc_total > p_max_files THEN
        RETURN QUERY SELECT 'limit_exceeded', NULL::UUID, NULL::UUID[], 'max_files_per_request';
        RETURN;
    END IF;

    -- 1. 租户受理锁：串行化同租户的受理与删除
    PERFORM 1 FROM tenants WHERE id = p_tenant_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'forbidden', NULL::UUID, NULL::UUID[], 'tenant_unknown';
        RETURN;
    END IF;

    -- 2. 文档存在性、租户归属与所有权
    SELECT count(*) INTO v_doc_count
    FROM documents d
    WHERE d.id = ANY(p_document_ids)
      AND d.tenant_id = p_tenant_id
      AND (p_is_admin OR d.user_id = p_requester_id);
    IF v_doc_count <> v_doc_total THEN
        RETURN QUERY SELECT 'not_found', NULL::UUID, NULL::UUID[], 'document_unavailable';
        RETURN;
    END IF;

    -- 3. 幂等键
    IF p_idempotency_key IS NOT NULL THEN
        SELECT jr.request_id, jr.request_fingerprint, jr.reused_from_request_id
        INTO v_request_id, v_existing_fingerprint, v_existing_reused_from
        FROM job_requests jr
        WHERE jr.tenant_id = p_tenant_id
          AND jr.requester_id = p_requester_id
          AND jr.capability = 'parse'
          AND jr.idempotency_key = p_idempotency_key;
        IF FOUND THEN
            IF v_existing_fingerprint = p_request_fingerprint THEN
                -- 别名行解析到其来源请求的 Job
                v_source_request_id := COALESCE(v_existing_reused_from, v_request_id);
                SELECT COALESCE(array_agg(j.job_id ORDER BY j.created_at, j.job_id), '{}')
                INTO v_job_ids
                FROM processing_jobs j
                WHERE j.request_id = v_source_request_id;
                RETURN QUERY SELECT 'reused', v_source_request_id, v_job_ids, 'idempotent_replay';
                RETURN;
            END IF;
            RETURN QUERY SELECT 'conflict', v_request_id, NULL::UUID[],
                'idempotency_key_reused_with_different_request';
            RETURN;
        END IF;
    END IF;

    -- 4. 活动请求冲突：文档集合有交集时，只有完全一致（发起人+指纹+集合）才复用
    FOR v_conflict IN
        SELECT jr.request_id, jr.request_fingerprint, jr.requester_id, jr.request_payload,
               array_agg(DISTINCT d.doc_id) AS doc_set
        FROM job_requests jr
        JOIN processing_jobs j
          ON j.request_id = jr.request_id
         AND j.status IN ('queued', 'processing')
        CROSS JOIN LATERAL unnest(j.document_ids) AS d(doc_id)
        WHERE jr.tenant_id = p_tenant_id
          AND jr.reused_from_request_id IS NULL
        GROUP BY jr.request_id, jr.request_fingerprint, jr.requester_id, jr.request_payload
        HAVING array_agg(DISTINCT d.doc_id) && p_document_ids
    LOOP
        IF v_conflict.doc_set @> p_document_ids
           AND v_conflict.doc_set <@ p_document_ids
           AND v_conflict.requester_id = p_requester_id
           AND v_conflict.request_fingerprint = p_request_fingerprint
           -- 执行等价：冻结规格完全一致（含策略版本与有效参数）
           AND v_conflict.request_payload = COALESCE(p_spec, '{}'::jsonb) THEN
            -- 新 Key 命中活动复用：落一条别名受理记录，保证终态后重试仍可找回
            IF p_idempotency_key IS NOT NULL THEN
                INSERT INTO job_requests (
                    tenant_id, requester_id, capability, idempotency_key,
                    request_fingerprint, request_payload, policy_version,
                    reused_from_request_id
                ) VALUES (
                    p_tenant_id, p_requester_id, 'parse', p_idempotency_key,
                    p_request_fingerprint, COALESCE(p_spec, '{}'::jsonb), p_policy_version,
                    v_conflict.request_id
                );
            END IF;
            SELECT COALESCE(array_agg(j.job_id ORDER BY j.created_at, j.job_id), '{}')
            INTO v_job_ids
            FROM processing_jobs j
            WHERE j.request_id = v_conflict.request_id;
            RETURN QUERY SELECT 'reused', v_conflict.request_id, v_job_ids, 'active_request_reused';
            RETURN;
        END IF;
        RETURN QUERY SELECT 'conflict', v_conflict.request_id, NULL::UUID[],
            'input_overlaps_active_request';
        RETURN;
    END LOOP;

    -- 5. 活动 Job 上限
    SELECT count(*) INTO v_active_count
    FROM processing_jobs
    WHERE tenant_id = p_tenant_id
      AND status IN ('queued', 'processing');
    IF v_active_count + v_doc_total > p_max_active_jobs THEN
        RETURN QUERY SELECT 'limit_exceeded', NULL::UUID, NULL::UUID[], 'max_active_jobs_per_tenant';
        RETURN;
    END IF;

    -- 6. 创建请求记录 + 每文件一个 Job
    INSERT INTO job_requests (
        tenant_id, requester_id, capability, idempotency_key,
        request_fingerprint, request_payload, policy_version
    ) VALUES (
        p_tenant_id, p_requester_id, 'parse', p_idempotency_key,
        p_request_fingerprint, COALESCE(p_spec, '{}'::jsonb), p_policy_version
    )
    RETURNING request_id INTO v_request_id;

    FOREACH v_doc_id IN ARRAY p_document_ids LOOP
        INSERT INTO processing_jobs (
            job_id, job_type, status, stage, progress, document_ids, error,
            created_by, tenant_id, execution_spec, request_id, created_at, updated_at
        ) VALUES (
            gen_random_uuid(), 'parse', 'queued', 'queued', 0, ARRAY[v_doc_id], NULL,
            p_requester_id, p_tenant_id,
            COALESCE(p_spec, '{}'::jsonb) || jsonb_build_object('document_id', v_doc_id),
            v_request_id, NOW(), NOW()
        )
        RETURNING job_id INTO v_new_job_id;
        v_job_ids := array_append(v_job_ids, v_new_job_id);
    END LOOP;

    RETURN QUERY SELECT 'ok', v_request_id, v_job_ids, NULL::TEXT;
END;
$$;

COMMENT ON FUNCTION admit_parse_request IS
    '受理 Parse 提交：租户锁内完成权限、幂等、活动冲突、上限检查，并创建请求记录与每文件一个 Job';

-- ############################################################
-- PART 5: 原子命令 —— 交卷（产物提交）
-- ############################################################

CREATE OR REPLACE FUNCTION commit_parse_job(
    p_job_id UUID,
    p_worker_id TEXT,
    p_attempts INT,
    p_outcome TEXT,
    p_error TEXT,
    p_parse_data JSONB
)
RETURNS TABLE (
    out_status TEXT,
    out_reason TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_job processing_jobs%ROWTYPE;
    v_document_id UUID;
BEGIN
    SELECT * INTO v_job
    FROM processing_jobs
    WHERE job_id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'not_found', 'job_unknown';
        RETURN;
    END IF;

    -- 幂等确认：已完成的成功产物不重复写入
    IF v_job.status = 'completed' AND p_outcome = 'ok' THEN
        IF EXISTS (
            SELECT 1 FROM results r
            WHERE r.job_id = p_job_id AND r.sample_key = 'parse'
        ) THEN
            RETURN QUERY SELECT 'already_committed', NULL::TEXT;
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
        v_document_id := (v_job.document_ids)[1];
        INSERT INTO results (
            tenant_id, job_id, document_id, config_revision_id,
            sample_key, data, field_meta, review_state
        ) VALUES (
            v_job.tenant_id, p_job_id, v_document_id, NULL,
            'parse', COALESCE(p_parse_data, '{}'::jsonb), '{}'::jsonb, 'pending'
        )
        ON CONFLICT (job_id) WHERE sample_key = 'parse' DO NOTHING;

        UPDATE processing_jobs
        SET status = 'completed',
            stage = 'completed',
            progress = 100,
            error = NULL,
            finished_at = NOW(),
            updated_at = NOW()
        WHERE job_id = p_job_id;

        RETURN QUERY SELECT 'completed', NULL::TEXT;
    ELSIF p_outcome = 'failed' THEN
        UPDATE processing_jobs
        SET status = 'failed',
            stage = 'failed',
            error = COALESCE(p_error, 'parse_failed'),
            finished_at = NOW(),
            updated_at = NOW()
        WHERE job_id = p_job_id;

        RETURN QUERY SELECT 'failed', NULL::TEXT;
    END IF;

    RETURN QUERY SELECT 'invalid', 'unknown_outcome';
END;
$$;

COMMENT ON FUNCTION commit_parse_job IS
    '交卷：锁 Job 行、校验认领令牌后写入规范产物或失败终态；失效令牌不得写入';

-- ############################################################
-- PART 6: 原子命令 —— 删除文档
-- ############################################################

CREATE OR REPLACE FUNCTION delete_document_guarded(
    p_document_id UUID,
    p_requester_id UUID,
    p_is_admin BOOLEAN
)
RETURNS TABLE (
    out_status TEXT,
    out_file_path TEXT,
    out_reason TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_doc documents%ROWTYPE;
BEGIN
    SELECT * INTO v_doc FROM documents WHERE id = p_document_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'not_found', NULL::TEXT, 'document_unknown';
        RETURN;
    END IF;

    -- 与受理相同的租户锁：避免"检查时无任务、删除前又入队"
    PERFORM 1 FROM tenants WHERE id = v_doc.tenant_id FOR NO KEY UPDATE;

    SELECT * INTO v_doc FROM documents WHERE id = p_document_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'not_found', NULL::TEXT, 'document_unknown';
        RETURN;
    END IF;

    IF NOT (p_is_admin OR v_doc.user_id = p_requester_id) THEN
        RETURN QUERY SELECT 'not_found', NULL::TEXT, 'document_unavailable';
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1 FROM processing_jobs j
        WHERE j.tenant_id = v_doc.tenant_id
          AND j.status IN ('queued', 'processing')
          AND j.document_ids @> ARRAY[p_document_id]
    ) THEN
        RETURN QUERY SELECT 'conflict', NULL::TEXT, 'document_in_active_job';
        RETURN;
    END IF;

    DELETE FROM documents WHERE id = p_document_id;

    -- 文件清理由调用方在事务提交后执行；失败进入重试清理路径
    RETURN QUERY SELECT 'ok', v_doc.file_path, NULL::TEXT;
END;
$$;

COMMENT ON FUNCTION delete_document_guarded IS
    '删除文档：租户锁内完成权限与活动占用检查后删除数据库行；返回文件路径供提交后清理';

-- ############################################################
-- PART 7: 函数执行权限（仅受信服务角色）
-- ############################################################

REVOKE ALL ON FUNCTION admit_parse_request(
    UUID, UUID, BOOLEAN, UUID[], JSONB, TEXT, TEXT, TEXT, INT, INT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION admit_parse_request(
    UUID, UUID, BOOLEAN, UUID[], JSONB, TEXT, TEXT, TEXT, INT, INT
) TO service_role;

REVOKE ALL ON FUNCTION commit_parse_job(
    UUID, TEXT, INT, TEXT, TEXT, JSONB
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION commit_parse_job(
    UUID, TEXT, INT, TEXT, TEXT, JSONB
) TO service_role;

REVOKE ALL ON FUNCTION delete_document_guarded(
    UUID, UUID, BOOLEAN
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION delete_document_guarded(
    UUID, UUID, BOOLEAN
) TO service_role;

SELECT pg_notify('pgrst', 'reload schema');
SELECT '024: Parse 受理记录、执行规格与原子命令就绪' AS message;
