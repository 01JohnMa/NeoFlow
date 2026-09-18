-- ============================================================
-- MIGRATION 025: 2.0 清场（#31）——删除审核 / Excel / Feishu / CRM / 旧抽取入口的数据库残留
-- ============================================================
-- 背景：
--   * 审核（review_state / field_meta）、Excel/Feishu 输出、CRM 链路、
--     旧抽取入口（documents.template_id / job_type 等）整体退出 NeoFlow 2.0；
--   * Parse 结果路径（results.sample_key='parse' 唯一索引）不受影响；
--   * 历史抽取数据仍保留在 results.data，仅删除审核与输出的元数据列。
--
-- 注意：processing_jobs.job_type 由 admit_parse_request 写入，
--   因此先重定义该 RPC，再删列。
-- ============================================================

-- ############ PART 0: 重定义 admit_parse_request（不再写入 job_type） ############

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
            job_id, status, stage, progress, document_ids, error,
            created_by, tenant_id, execution_spec, request_id, created_at, updated_at
        ) VALUES (
            gen_random_uuid(), 'queued', 'queued', 0, ARRAY[v_doc_id], NULL,
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

-- ############ PART 0b: 重定义 commit_parse_job（产物不再写入审核列） ############

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
            sample_key, data
        ) VALUES (
            v_job.tenant_id, p_job_id, v_document_id, NULL,
            'parse', COALESCE(p_parse_data, '{}'::jsonb)
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

-- ############ PART 1: results 审核元数据 ############

ALTER TABLE results DROP COLUMN IF EXISTS review_state;
ALTER TABLE results DROP COLUMN IF EXISTS field_meta;

-- ############ PART 2: documents 旧抽取/OCR 命名残留 ############

ALTER TABLE documents DROP COLUMN IF EXISTS template_id;
ALTER TABLE documents DROP COLUMN IF EXISTS ocr_text;
ALTER TABLE documents DROP COLUMN IF EXISTS ocr_confidence;
ALTER TABLE documents DROP COLUMN IF EXISTS custom_push_name;

-- 历史审核态收敛：审核入口删除后 pending_review 无出口，统一为 completed
UPDATE documents SET status = 'completed', updated_at = NOW()
WHERE status = 'pending_review';

-- ############ PART 3: processing_jobs 旧 Job 字段 ############

ALTER TABLE processing_jobs DROP COLUMN IF EXISTS job_type;
ALTER TABLE processing_jobs DROP COLUMN IF EXISTS items;
ALTER TABLE processing_jobs DROP COLUMN IF EXISTS dedupe_key;

-- ############ PART 4: Feishu 推送去重表 ############

DROP TABLE IF EXISTS feishu_push_records;

-- ############ PART 5: configurations draft_definition JSONB 数据迁移 ############
-- 历史 configuration_revisions.definition 是受触发器保护的不可变快照，不回改；
-- 读取侧只取已知键，遗留键不参与任何执行。

UPDATE configurations
SET draft_definition = draft_definition
    - 'extraction_mode' - 'output_mode' - 'push_attachment' - 'auto_approve' - 'feishu' - 'excel'
WHERE draft_definition ?| array['extraction_mode', 'output_mode', 'push_attachment', 'auto_approve', 'feishu', 'excel'];

UPDATE configurations
SET draft_definition = jsonb_set(
        draft_definition,
        '{fields}',
        COALESCE((
            SELECT jsonb_agg(f - 'review_enforced' - 'review_allowed_values' - 'feishu_column')
            FROM jsonb_array_elements(draft_definition -> 'fields') AS f
        ), '[]'::jsonb)
    )
WHERE jsonb_typeof(draft_definition -> 'fields') = 'array';

SELECT pg_notify('pgrst', 'reload schema');
SELECT '025: 2.0 清场（审核/输出/CRM/旧抽取入口）就绪' AS message;
