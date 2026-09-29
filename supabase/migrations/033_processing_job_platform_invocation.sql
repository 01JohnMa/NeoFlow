-- 平台模型归因：processing_jobs 保存 AI Center 父 Invocation 引用。
--
-- Parse/Extract 受理时（202 返回前）把 x-ai-center-invocation-id 固化到每个 Job：
-- - Worker 在初始 HTTP 请求结束后仍能以该 Invocation 经 Relay 访问模型；
-- - 重试/重启只从数据库恢复引用，查询 Job 状态不会覆盖原始 Invocation；
-- - 只保存 opaque 引用，不复制 application/version/caller/secret。
--
-- admit_parse_request 增加 p_platform_invocation_id（DEFAULT NULL 保持旧调用兼容）。

ALTER TABLE processing_jobs
    ADD COLUMN IF NOT EXISTS platform_invocation_id UUID;

COMMENT ON COLUMN processing_jobs.platform_invocation_id IS
    'AI Center 平台父 Invocation 引用（opaque）；平台模式下模型调用按此归因，历史 Job 为 NULL';

CREATE INDEX IF NOT EXISTS idx_processing_jobs_platform_invocation
    ON processing_jobs(platform_invocation_id)
    WHERE platform_invocation_id IS NOT NULL;

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
    p_max_active_jobs INT,
    p_platform_invocation_id UUID DEFAULT NULL
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
            created_by, tenant_id, execution_spec, request_id,
            platform_invocation_id, created_at, updated_at
        ) VALUES (
            gen_random_uuid(), 'parse', 'queued', 'queued', 0, ARRAY[v_doc_id], NULL,
            p_requester_id, p_tenant_id,
            COALESCE(p_spec, '{}'::jsonb) || jsonb_build_object('document_id', v_doc_id),
            v_request_id,
            p_platform_invocation_id, NOW(), NOW()
        )
        RETURNING job_id INTO v_new_job_id;
        v_job_ids := array_append(v_job_ids, v_new_job_id);
    END LOOP;

    RETURN QUERY SELECT 'ok', v_request_id, v_job_ids, NULL::TEXT;
END;
$$;

COMMENT ON FUNCTION admit_parse_request IS
    '受理 Parse 提交：租户锁内完成权限、幂等、活动冲突、上限检查，并创建请求记录与每文件一个 Job；'
    'p_platform_invocation_id 固化 AI Center 父 Invocation 引用到每个 Job';
