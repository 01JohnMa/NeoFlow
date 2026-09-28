-- NeoFlow fresh-install baseline generated from the verified PostgreSQL 16 public schema.
-- This file is for an empty database only. Existing databases use the historical
-- supabase/migrations chain and must not re-run this baseline.
-- Auth tables remain owned by GoTrue; only NeoFlow compatibility helpers are defined.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS auth;

CREATE OR REPLACE FUNCTION auth.role()
RETURNS text LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('request.jwt.claim.role', true), '');
$$;
CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;
CREATE OR REPLACE FUNCTION auth.jwt()
RETURNS jsonb LANGUAGE sql STABLE AS $$
  SELECT COALESCE(NULLIF(current_setting('request.jwt.claims', true), ''), '{}')::jsonb;
$$;

--
-- PostgreSQL database dump
--


-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

-- public schema is created by PostgreSQL/Supabase


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: admit_parse_request(uuid, uuid, boolean, uuid[], jsonb, text, text, text, integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.admit_parse_request(p_tenant_id uuid, p_requester_id uuid, p_is_admin boolean, p_document_ids uuid[], p_spec jsonb, p_idempotency_key text, p_request_fingerprint text, p_policy_version text, p_max_files integer, p_max_active_jobs integer) RETURNS TABLE(out_status text, out_request_id uuid, out_job_ids uuid[], out_reason text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
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


--
-- Name: FUNCTION admit_parse_request(p_tenant_id uuid, p_requester_id uuid, p_is_admin boolean, p_document_ids uuid[], p_spec jsonb, p_idempotency_key text, p_request_fingerprint text, p_policy_version text, p_max_files integer, p_max_active_jobs integer); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.admit_parse_request(p_tenant_id uuid, p_requester_id uuid, p_is_admin boolean, p_document_ids uuid[], p_spec jsonb, p_idempotency_key text, p_request_fingerprint text, p_policy_version text, p_max_files integer, p_max_active_jobs integer) IS '受理 Parse 提交：租户锁内完成权限、幂等、活动冲突、上限检查，并创建请求记录与每文件一个 Job';


--
-- Name: bind_extract_parse_result(uuid, text, integer, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.bind_extract_parse_result(p_job_id uuid, p_worker_id text, p_attempts integer, p_result_id uuid) RETURNS TABLE(out_status text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
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


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: processing_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.processing_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_id uuid NOT NULL,
    status character varying(50) DEFAULT 'queued'::character varying NOT NULL,
    stage character varying(50) DEFAULT 'queued'::character varying NOT NULL,
    progress integer DEFAULT 0 NOT NULL,
    document_ids uuid[] DEFAULT ARRAY[]::uuid[],
    total integer DEFAULT 0 NOT NULL,
    completed_count integer DEFAULT 0 NOT NULL,
    error text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    locked_by text,
    locked_at timestamp with time zone,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    configuration_revision_id uuid,
    tenant_id uuid,
    execution_spec jsonb,
    request_id uuid,
    parse_result_id uuid,
    execution_budget jsonb,
    CONSTRAINT processing_jobs_status_check CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'pending'::character varying, 'processing'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: COLUMN processing_jobs.execution_spec; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.processing_jobs.execution_spec IS '不可变执行规格（参数化能力）：capability/spec_version/document_id/input_selection/effective_params/policy_version；历史 Job 为 NULL';


--
-- Name: COLUMN processing_jobs.request_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.processing_jobs.request_id IS '受理台账引用：本次 Job 由哪次提交创建；历史 Job 为 NULL';


--
-- Name: claim_next_processing_job(text, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.claim_next_processing_job(p_worker_id text, p_stale_after_seconds integer DEFAULT 1800) RETURNS SETOF public.processing_jobs
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    WITH next_job AS (
        SELECT id
        FROM processing_jobs
        WHERE (
              status = 'queued'
              OR (
                  status = 'processing'
                  AND locked_at < NOW() - make_interval(secs => p_stale_after_seconds)
              )
          )
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE processing_jobs AS job
    SET
        status = 'processing',
        stage = 'pending',
        progress = 5,
        locked_by = p_worker_id,
        locked_at = NOW(),
        started_at = COALESCE(job.started_at, NOW()),
        attempts = job.attempts + 1,
        updated_at = NOW()
    FROM next_job
    WHERE job.id = next_job.id
    RETURNING job.*;
END;
$$;


--
-- Name: commit_extract_job(uuid, text, integer, text, text, jsonb, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.commit_extract_job(p_job_id uuid, p_worker_id text, p_attempts integer, p_outcome text, p_error text, p_extract_data jsonb, p_engine jsonb) RETURNS TABLE(out_status text, out_reason text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
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
          AND r.job_id = p_job_id
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
        IF p_engine IS NULL OR jsonb_typeof(p_engine) <> 'object' THEN
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


--
-- Name: commit_extract_parse_result(uuid, text, integer, jsonb, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.commit_extract_parse_result(p_job_id uuid, p_worker_id text, p_attempts integer, p_parse_data jsonb, p_engine jsonb) RETURNS TABLE(out_status text, out_parse_result_id uuid, out_reason text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
DECLARE
    v_job processing_jobs%ROWTYPE;
    v_document_id UUID;
    v_result_id UUID;
    v_deadline TIMESTAMPTZ;
BEGIN
    SELECT * INTO v_job FROM processing_jobs WHERE job_id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'not_found', NULL::UUID, 'job_unknown'; RETURN;
    END IF;

    IF v_job.status <> 'processing'
       OR v_job.locked_by IS DISTINCT FROM p_worker_id
       OR v_job.attempts IS DISTINCT FROM p_attempts THEN
        RETURN QUERY SELECT 'stale_token', NULL::UUID, 'claim_ownership_lost'; RETURN;
    END IF;
    IF v_job.parse_result_id IS NOT NULL THEN
        SELECT id INTO v_result_id FROM results
        WHERE id = v_job.parse_result_id AND job_id = p_job_id AND sample_key = 'parse';
        IF FOUND THEN
            RETURN QUERY SELECT 'already_bound', v_result_id, NULL::TEXT; RETURN;
        END IF;
        RETURN QUERY SELECT 'invalid', NULL::UUID, 'binding_invalid'; RETURN;
    END IF;
    v_deadline := NULLIF(v_job.execution_budget->>'deadline', '')::TIMESTAMPTZ;
    IF v_deadline IS NOT NULL AND NOW() > v_deadline THEN
        RETURN QUERY SELECT 'expired', NULL::UUID, 'deadline_exceeded'; RETURN;
    END IF;
    IF v_job.document_ids IS NULL OR array_length(v_job.document_ids, 1) IS DISTINCT FROM 1 THEN
        RETURN QUERY SELECT 'invalid', NULL::UUID, 'document_count_invalid'; RETURN;
    END IF;
    IF p_parse_data IS NULL OR jsonb_typeof(p_parse_data) <> 'object' THEN
        RETURN QUERY SELECT 'invalid', NULL::UUID, 'parse_data_invalid'; RETURN;
    END IF;
    v_document_id := (v_job.document_ids)[1];

    INSERT INTO results (tenant_id, job_id, document_id, config_revision_id, sample_key, data, engine)
    VALUES (v_job.tenant_id, p_job_id, v_document_id, v_job.configuration_revision_id,
            'parse', p_parse_data, COALESCE(p_engine, '{}'::JSONB))
    ON CONFLICT (job_id) WHERE sample_key = 'parse'
    DO UPDATE SET data = EXCLUDED.data, engine = EXCLUDED.engine, updated_at = NOW()
    RETURNING id INTO v_result_id;

    UPDATE processing_jobs
    SET parse_result_id = v_result_id, stage = 'binding', progress = GREATEST(progress, 10), updated_at = NOW()
    WHERE job_id = p_job_id;
    RETURN QUERY SELECT 'bound', v_result_id, NULL::TEXT;
END;
$$;


--
-- Name: commit_parse_job(uuid, text, integer, text, text, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.commit_parse_job(p_job_id uuid, p_worker_id text, p_attempts integer, p_outcome text, p_error text, p_parse_data jsonb) RETURNS TABLE(out_status text, out_reason text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
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


--
-- Name: FUNCTION commit_parse_job(p_job_id uuid, p_worker_id text, p_attempts integer, p_outcome text, p_error text, p_parse_data jsonb); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.commit_parse_job(p_job_id uuid, p_worker_id text, p_attempts integer, p_outcome text, p_error text, p_parse_data jsonb) IS '交卷：锁 Job 行、校验认领令牌后写入规范产物或失败终态；失效令牌不得写入';


--
-- Name: consume_extract_request(uuid, text, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.consume_extract_request(p_job_id uuid, p_worker_id text, p_attempts integer) RETURNS TABLE(out_allowed boolean, out_reason text, out_requests_used integer, out_max_requests integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
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


--
-- Name: delete_document_guarded(uuid, uuid, boolean); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.delete_document_guarded(p_document_id uuid, p_requester_id uuid, p_is_admin boolean) RETURNS TABLE(out_status text, out_file_path text, out_reason text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
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


--
-- Name: FUNCTION delete_document_guarded(p_document_id uuid, p_requester_id uuid, p_is_admin boolean); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.delete_document_guarded(p_document_id uuid, p_requester_id uuid, p_is_admin boolean) IS '删除文档：租户锁内完成权限与活动占用检查后删除数据库行；返回文件路径供提交后清理';


--
-- Name: ensure_extract_budget(uuid, text, integer, integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.ensure_extract_budget(p_job_id uuid, p_worker_id text, p_attempts integer, p_max_requests integer, p_timeout_seconds integer) RETURNS TABLE(out_status text, out_requests_used integer, out_max_requests integer, out_deadline timestamp with time zone)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
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


--
-- Name: get_current_user_role(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_current_user_role() RETURNS character varying
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
BEGIN
    RETURN (SELECT role FROM profiles WHERE id = auth.uid());
END;
$$;


--
-- Name: get_current_user_tenant_id(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_current_user_tenant_id() RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
BEGIN
    RETURN (SELECT tenant_id FROM profiles WHERE id = auth.uid());
END;
$$;


--
-- Name: handle_new_user(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.handle_new_user() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
DECLARE
    v_tenant_id UUID;
BEGIN
    -- 从 raw_user_meta_data 中获取 tenant_id（注册时传入）
    v_tenant_id := (NEW.raw_user_meta_data->>'tenant_id')::UUID;

    INSERT INTO public.profiles (id, tenant_id, role, display_name)
    VALUES (
        NEW.id,
        v_tenant_id,
        'user',
        COALESCE(NEW.raw_user_meta_data->>'display_name', NEW.email)
    );
    RETURN NEW;
EXCEPTION WHEN invalid_text_representation THEN
    -- 如果 tenant_id 格式无效，忽略它
    INSERT INTO public.profiles (id, role, display_name)
    VALUES (
        NEW.id,
        'user',
        COALESCE(NEW.raw_user_meta_data->>'display_name', NEW.email)
    );
    RETURN NEW;
END;
$$;


--
-- Name: prevent_configuration_revision_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.prevent_configuration_revision_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'configuration_revisions 不可修改（immutable snapshot）';
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: configuration_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.configuration_revisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    configuration_id uuid NOT NULL,
    revision_number integer NOT NULL,
    definition jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    published_at timestamp with time zone
);


--
-- Name: configurations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.configurations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name character varying(100) NOT NULL,
    code character varying(50),
    description text,
    type character varying(20) DEFAULT 'extract'::character varying NOT NULL,
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    draft_definition jsonb DEFAULT '{}'::jsonb NOT NULL,
    current_revision_id uuid,
    legacy_template_id uuid,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT configurations_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'published'::character varying, 'archived'::character varying])::text[]))),
    CONSTRAINT configurations_type_check CHECK (((type)::text = ANY ((ARRAY['parse'::character varying, 'extract'::character varying, 'classify'::character varying, 'split'::character varying, 'composite'::character varying])::text[])))
);


--
-- Name: document_page_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_page_embeddings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    document_id uuid NOT NULL,
    parse_result_id uuid NOT NULL,
    source_document_hash text NOT NULL,
    physical_page_no integer NOT NULL,
    page_state text NOT NULL,
    page_source text,
    page_text text,
    page_text_hash text,
    text_profile_hash text NOT NULL,
    embedding_profile_hash text NOT NULL,
    embedding jsonb,
    embedding_dimension integer,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT document_page_embeddings_page_state_check CHECK ((page_state = ANY (ARRAY['parsed'::text, 'blank'::text, 'parse_failed'::text, 'unknown'::text, 'unencoded'::text]))),
    CONSTRAINT document_page_embeddings_physical_page_no_check CHECK ((physical_page_no > 0)),
    CONSTRAINT page_embedding_state_consistency CHECK ((((page_state = 'parsed'::text) AND (page_text IS NOT NULL) AND (page_text_hash IS NOT NULL)) OR (page_state <> 'parsed'::text))),
    CONSTRAINT page_embedding_vector_consistency CHECK ((((embedding IS NULL) AND (embedding_dimension IS NULL)) OR ((jsonb_typeof(embedding) = 'array'::text) AND (embedding_dimension IS NOT NULL) AND (embedding_dimension > 0))))
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    file_name character varying(500) NOT NULL,
    original_file_name character varying(500),
    display_name character varying(255),
    file_path character varying(1000) NOT NULL,
    file_size bigint,
    file_type character varying(100),
    file_extension character varying(50),
    mime_type character varying(100),
    document_type character varying(50),
    status character varying(50) DEFAULT 'pending'::character varying,
    error_message text,
    source_document_ids uuid[],
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    processed_at timestamp with time zone,
    tenant_id uuid,
    CONSTRAINT documents_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'uploaded'::character varying, 'queued'::character varying, 'processing'::character varying, 'pending_review'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: job_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_requests (
    request_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    requester_id uuid NOT NULL,
    capability character varying(50) NOT NULL,
    idempotency_key text,
    request_fingerprint text NOT NULL,
    request_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    policy_version text NOT NULL,
    reused_from_request_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_requests_capability_check CHECK (((capability)::text = 'parse'::text))
);


--
-- Name: TABLE job_requests; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.job_requests IS '能力受理台账：一次提交一条；幂等键与请求指纹用于重试判定，Job 通过 request_id 归属到请求';


--
-- Name: processing_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.processing_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    document_id uuid,
    step character varying(100) NOT NULL,
    status character varying(50) NOT NULL,
    message text,
    error_details text,
    duration_ms integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.profiles (
    id uuid NOT NULL,
    tenant_id uuid,
    role character varying(20) DEFAULT 'user'::character varying,
    display_name character varying(100),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT profiles_role_check CHECK (((role)::text = ANY ((ARRAY['super_admin'::character varying, 'tenant_admin'::character varying, 'user'::character varying])::text[])))
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    is_default boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.results (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    job_id uuid,
    document_id uuid,
    config_revision_id uuid,
    sample_key text DEFAULT 'default'::text NOT NULL,
    data jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    engine jsonb
);



--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(100) NOT NULL,
    code character varying(50) NOT NULL,
    description text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: configuration_revisions configuration_revisions_configuration_id_revision_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuration_revisions
    ADD CONSTRAINT configuration_revisions_configuration_id_revision_number_key UNIQUE (configuration_id, revision_number);


--
-- Name: configuration_revisions configuration_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuration_revisions
    ADD CONSTRAINT configuration_revisions_pkey PRIMARY KEY (id);


--
-- Name: configurations configurations_legacy_template_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configurations
    ADD CONSTRAINT configurations_legacy_template_id_key UNIQUE (legacy_template_id);


--
-- Name: configurations configurations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configurations
    ADD CONSTRAINT configurations_pkey PRIMARY KEY (id);


--
-- Name: configurations configurations_tenant_id_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configurations
    ADD CONSTRAINT configurations_tenant_id_code_key UNIQUE (tenant_id, code);


--
-- Name: document_page_embeddings document_page_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_page_embeddings
    ADD CONSTRAINT document_page_embeddings_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: job_requests job_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_requests
    ADD CONSTRAINT job_requests_pkey PRIMARY KEY (request_id);


--
-- Name: processing_jobs processing_jobs_job_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_jobs
    ADD CONSTRAINT processing_jobs_job_id_key UNIQUE (job_id);


--
-- Name: processing_jobs processing_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_jobs
    ADD CONSTRAINT processing_jobs_pkey PRIMARY KEY (id);


--
-- Name: processing_logs processing_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_logs
    ADD CONSTRAINT processing_logs_pkey PRIMARY KEY (id);


--
-- Name: profiles profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: results results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.results
    ADD CONSTRAINT results_pkey PRIMARY KEY (id);



--
-- Name: tenants tenants_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_code_key UNIQUE (code);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: idx_configuration_revisions_configuration_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_configuration_revisions_configuration_id ON public.configuration_revisions USING btree (configuration_id);


--
-- Name: idx_configurations_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_configurations_project_id ON public.configurations USING btree (project_id);


--
-- Name: idx_configurations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_configurations_status ON public.configurations USING btree (status);


--
-- Name: idx_configurations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_configurations_tenant_id ON public.configurations USING btree (tenant_id);


--
-- Name: idx_configurations_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_configurations_type ON public.configurations USING btree (type);


--
-- Name: idx_documents_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_created_at ON public.documents USING btree (created_at DESC);


--
-- Name: idx_documents_document_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_document_type ON public.documents USING btree (document_type);


--
-- Name: idx_documents_source_document_ids; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_source_document_ids ON public.documents USING gin (source_document_ids);


--
-- Name: idx_documents_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_status ON public.documents USING btree (status);


--
-- Name: idx_documents_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_tenant_id ON public.documents USING btree (tenant_id);


--
-- Name: idx_documents_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_user_id ON public.documents USING btree (user_id);


--
-- Name: idx_job_requests_tenant_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_requests_tenant_created_at ON public.job_requests USING btree (tenant_id, created_at DESC);


--
-- Name: idx_page_embedding_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_page_embedding_document ON public.document_page_embeddings USING btree (tenant_id, document_id, source_document_hash, physical_page_no);


--
-- Name: idx_page_embedding_parse_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_page_embedding_parse_result ON public.document_page_embeddings USING btree (tenant_id, parse_result_id);


--
-- Name: idx_processing_jobs_configuration_revision_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_processing_jobs_configuration_revision_id ON public.processing_jobs USING btree (configuration_revision_id);


--
-- Name: idx_processing_jobs_parse_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_processing_jobs_parse_result ON public.processing_jobs USING btree (parse_result_id);


--
-- Name: idx_processing_jobs_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_processing_jobs_request_id ON public.processing_jobs USING btree (request_id);


--
-- Name: idx_processing_jobs_status_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_processing_jobs_status_created_at ON public.processing_jobs USING btree (status, created_at DESC);


--
-- Name: idx_processing_jobs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_processing_jobs_tenant_id ON public.processing_jobs USING btree (tenant_id);


--
-- Name: idx_processing_jobs_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_processing_jobs_tenant_status ON public.processing_jobs USING btree (tenant_id, status);


--
-- Name: idx_processing_jobs_worker_claim; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_processing_jobs_worker_claim ON public.processing_jobs USING btree (status, locked_at, created_at);


--
-- Name: idx_processing_logs_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_processing_logs_document_id ON public.processing_logs USING btree (document_id);


--
-- Name: idx_processing_logs_step; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_processing_logs_step ON public.processing_logs USING btree (step);


--
-- Name: idx_profiles_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_profiles_role ON public.profiles USING btree (role);


--
-- Name: idx_profiles_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_profiles_tenant_id ON public.profiles USING btree (tenant_id);


--
-- Name: idx_projects_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_projects_tenant_id ON public.projects USING btree (tenant_id);


--
-- Name: idx_results_config_revision_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_results_config_revision_id ON public.results USING btree (config_revision_id);


--
-- Name: idx_results_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_results_document_id ON public.results USING btree (document_id);


--
-- Name: idx_results_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_results_job_id ON public.results USING btree (job_id);


--
-- Name: idx_results_tenant_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_results_tenant_created_at ON public.results USING btree (tenant_id, created_at DESC);


--
-- Name: idx_tenants_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tenants_code ON public.tenants USING btree (code);


--
-- Name: idx_tenants_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tenants_is_active ON public.tenants USING btree (is_active);


--
-- Name: results_extract_job_uniq; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX results_extract_job_uniq ON public.results USING btree (job_id) WHERE (sample_key = 'extract'::text);


--
-- Name: uq_job_requests_idempotency; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_job_requests_idempotency ON public.job_requests USING btree (tenant_id, requester_id, capability, idempotency_key) WHERE (idempotency_key IS NOT NULL);


--
-- Name: uq_page_embedding_identity; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_page_embedding_identity ON public.document_page_embeddings USING btree (tenant_id, document_id, parse_result_id, source_document_hash, physical_page_no, text_profile_hash, embedding_profile_hash);


--
-- Name: uq_projects_tenant_default; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_projects_tenant_default ON public.projects USING btree (tenant_id) WHERE is_default;


--
-- Name: uq_results_parse_job; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_results_parse_job ON public.results USING btree (job_id) WHERE (sample_key = 'parse'::text);


--
-- Name: configuration_revisions trg_configuration_revisions_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_configuration_revisions_immutable BEFORE UPDATE ON public.configuration_revisions FOR EACH ROW EXECUTE FUNCTION public.prevent_configuration_revision_update();


--
-- Name: configurations update_configurations_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_configurations_updated_at BEFORE UPDATE ON public.configurations FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: document_page_embeddings update_document_page_embeddings_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_document_page_embeddings_updated_at BEFORE UPDATE ON public.document_page_embeddings FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: documents update_documents_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON public.documents FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: profiles update_profiles_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: projects update_projects_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON public.projects FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: results update_results_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_results_updated_at BEFORE UPDATE ON public.results FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: tenants update_tenants_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON public.tenants FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: configuration_revisions configuration_revisions_configuration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuration_revisions
    ADD CONSTRAINT configuration_revisions_configuration_id_fkey FOREIGN KEY (configuration_id) REFERENCES public.configurations(id) ON DELETE CASCADE;


--
-- Name: configurations configurations_current_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configurations
    ADD CONSTRAINT configurations_current_revision_id_fkey FOREIGN KEY (current_revision_id) REFERENCES public.configuration_revisions(id) ON DELETE SET NULL;


--
-- Name: configurations configurations_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configurations
    ADD CONSTRAINT configurations_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: configurations configurations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configurations
    ADD CONSTRAINT configurations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: document_page_embeddings document_page_embeddings_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_page_embeddings
    ADD CONSTRAINT document_page_embeddings_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: document_page_embeddings document_page_embeddings_parse_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_page_embeddings
    ADD CONSTRAINT document_page_embeddings_parse_result_id_fkey FOREIGN KEY (parse_result_id) REFERENCES public.results(id) ON DELETE RESTRICT;


--
-- Name: document_page_embeddings document_page_embeddings_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_page_embeddings
    ADD CONSTRAINT document_page_embeddings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: documents documents_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: job_requests job_requests_reused_from_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_requests
    ADD CONSTRAINT job_requests_reused_from_request_id_fkey FOREIGN KEY (reused_from_request_id) REFERENCES public.job_requests(request_id) ON DELETE SET NULL;


--
-- Name: job_requests job_requests_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_requests
    ADD CONSTRAINT job_requests_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: processing_jobs processing_jobs_configuration_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_jobs
    ADD CONSTRAINT processing_jobs_configuration_revision_id_fkey FOREIGN KEY (configuration_revision_id) REFERENCES public.configuration_revisions(id) ON DELETE SET NULL;


--
-- Name: processing_jobs processing_jobs_parse_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_jobs
    ADD CONSTRAINT processing_jobs_parse_result_id_fkey FOREIGN KEY (parse_result_id) REFERENCES public.results(id) ON DELETE RESTRICT;


--
-- Name: processing_jobs processing_jobs_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_jobs
    ADD CONSTRAINT processing_jobs_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.job_requests(request_id) ON DELETE SET NULL;


--
-- Name: processing_jobs processing_jobs_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_jobs
    ADD CONSTRAINT processing_jobs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: processing_logs processing_logs_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_logs
    ADD CONSTRAINT processing_logs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: profiles profiles_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: projects projects_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: results results_config_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.results
    ADD CONSTRAINT results_config_revision_id_fkey FOREIGN KEY (config_revision_id) REFERENCES public.configuration_revisions(id) ON DELETE SET NULL;


--
-- Name: results results_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.results
    ADD CONSTRAINT results_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: results results_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.results
    ADD CONSTRAINT results_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.processing_jobs(job_id) ON DELETE SET NULL;


--
-- Name: results results_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.results
    ADD CONSTRAINT results_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: tenants Anyone can view active tenants; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Anyone can view active tenants" ON public.tenants FOR SELECT USING ((is_active = true));


--
-- Name: documents Service role can manage all documents; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role can manage all documents" ON public.documents USING ((auth.role() = 'service_role'::text));


--
-- Name: processing_jobs Service role can manage all processing_jobs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role can manage all processing_jobs" ON public.processing_jobs USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: processing_logs Service role can manage all processing_logs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role can manage all processing_logs" ON public.processing_logs USING ((auth.role() = 'service_role'::text));


--
-- Name: configuration_revisions Service role full access to configuration_revisions; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to configuration_revisions" ON public.configuration_revisions USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: configurations Service role full access to configurations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to configurations" ON public.configurations USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: document_page_embeddings Service role full access to document_page_embeddings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to document_page_embeddings" ON public.document_page_embeddings USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: job_requests Service role full access to job_requests; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to job_requests" ON public.job_requests USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: profiles Service role full access to profiles; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to profiles" ON public.profiles USING ((auth.role() = 'service_role'::text));


--
-- Name: projects Service role full access to projects; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to projects" ON public.projects USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: results Service role full access to results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to results" ON public.results USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: tenants Service role full access to tenants; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to tenants" ON public.tenants USING ((auth.role() = 'service_role'::text));


--
-- Name: tenants Super admin can manage all tenants; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Super admin can manage all tenants" ON public.tenants USING (((public.get_current_user_role())::text = 'super_admin'::text));


--
-- Name: documents Super admin can view all documents; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Super admin can view all documents" ON public.documents USING (((public.get_current_user_role())::text = 'super_admin'::text));


--
-- Name: profiles Super admin can view all profiles; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Super admin can view all profiles" ON public.profiles FOR SELECT USING (((public.get_current_user_role())::text = 'super_admin'::text));


--
-- Name: documents Tenant admin can view tenant documents; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Tenant admin can view tenant documents" ON public.documents FOR SELECT USING (((tenant_id = public.get_current_user_tenant_id()) AND ((public.get_current_user_role())::text = ANY ((ARRAY['tenant_admin'::character varying, 'super_admin'::character varying])::text[]))));


--
-- Name: profiles Tenant admin can view tenant profiles; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Tenant admin can view tenant profiles" ON public.profiles FOR SELECT USING (((tenant_id = public.get_current_user_tenant_id()) AND ((public.get_current_user_role())::text = ANY ((ARRAY['tenant_admin'::character varying, 'super_admin'::character varying])::text[]))));


--
-- Name: configurations Tenant admins can manage configurations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Tenant admins can manage configurations" ON public.configurations USING ((((public.get_current_user_role())::text = 'super_admin'::text) OR ((tenant_id = public.get_current_user_tenant_id()) AND ((public.get_current_user_role())::text = ANY ((ARRAY['tenant_admin'::character varying, 'super_admin'::character varying])::text[]))))) WITH CHECK ((((public.get_current_user_role())::text = 'super_admin'::text) OR ((tenant_id = public.get_current_user_tenant_id()) AND ((public.get_current_user_role())::text = ANY ((ARRAY['tenant_admin'::character varying, 'super_admin'::character varying])::text[])))));


--
-- Name: projects Tenant admins can manage projects; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Tenant admins can manage projects" ON public.projects USING ((((public.get_current_user_role())::text = 'super_admin'::text) OR ((tenant_id = public.get_current_user_tenant_id()) AND ((public.get_current_user_role())::text = ANY ((ARRAY['tenant_admin'::character varying, 'super_admin'::character varying])::text[]))))) WITH CHECK ((((public.get_current_user_role())::text = 'super_admin'::text) OR ((tenant_id = public.get_current_user_tenant_id()) AND ((public.get_current_user_role())::text = ANY ((ARRAY['tenant_admin'::character varying, 'super_admin'::character varying])::text[])))));


--
-- Name: results Tenant admins can manage results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Tenant admins can manage results" ON public.results USING ((((public.get_current_user_role())::text = 'super_admin'::text) OR ((tenant_id = public.get_current_user_tenant_id()) AND ((public.get_current_user_role())::text = ANY ((ARRAY['tenant_admin'::character varying, 'super_admin'::character varying])::text[]))))) WITH CHECK ((((public.get_current_user_role())::text = 'super_admin'::text) OR ((tenant_id = public.get_current_user_tenant_id()) AND ((public.get_current_user_role())::text = ANY ((ARRAY['tenant_admin'::character varying, 'super_admin'::character varying])::text[])))));


--
-- Name: configuration_revisions Tenant members can view configuration_revisions; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Tenant members can view configuration_revisions" ON public.configuration_revisions FOR SELECT USING ((((public.get_current_user_role())::text = 'super_admin'::text) OR (configuration_id IN ( SELECT configurations.id
   FROM public.configurations
  WHERE (configurations.tenant_id = public.get_current_user_tenant_id())))));


--
-- Name: configurations Tenant members can view configurations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Tenant members can view configurations" ON public.configurations FOR SELECT USING (((tenant_id = public.get_current_user_tenant_id()) OR ((public.get_current_user_role())::text = 'super_admin'::text)));


--
-- Name: projects Tenant members can view projects; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Tenant members can view projects" ON public.projects FOR SELECT USING (((tenant_id = public.get_current_user_tenant_id()) OR ((public.get_current_user_role())::text = 'super_admin'::text)));


--
-- Name: results Tenant members can view results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Tenant members can view results" ON public.results FOR SELECT USING (((tenant_id = public.get_current_user_tenant_id()) OR ((public.get_current_user_role())::text = 'super_admin'::text)));


--
-- Name: documents Users can manage own documents; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can manage own documents" ON public.documents USING (((user_id = auth.uid()) AND ((tenant_id IS NULL) OR (tenant_id = public.get_current_user_tenant_id()))));


--
-- Name: profiles Users can update own profile; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own profile" ON public.profiles FOR UPDATE USING ((id = auth.uid())) WITH CHECK (((id = auth.uid()) AND ((role)::text = (public.get_current_user_role())::text) AND (NOT (tenant_id IS DISTINCT FROM public.get_current_user_tenant_id()))));


--
-- Name: profiles Users can view own profile; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can view own profile" ON public.profiles FOR SELECT USING (((id = auth.uid()) OR ((public.get_current_user_role())::text = 'super_admin'::text)));


--
-- Name: configuration_revisions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.configuration_revisions ENABLE ROW LEVEL SECURITY;

--
-- Name: configurations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.configurations ENABLE ROW LEVEL SECURITY;

--
-- Name: document_page_embeddings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.document_page_embeddings ENABLE ROW LEVEL SECURITY;

--
-- Name: documents; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

--
-- Name: job_requests; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.job_requests ENABLE ROW LEVEL SECURITY;

--
-- Name: processing_jobs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;

--
-- Name: processing_logs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.processing_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: profiles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

--
-- Name: projects; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

--
-- Name: results; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.results ENABLE ROW LEVEL SECURITY;


--
-- Name: tenants; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;

--
-- Name: processing_logs 用户可以查看自己文档的处理日志; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "用户可以查看自己文档的处理日志" ON public.processing_logs USING ((document_id IN ( SELECT documents.id
   FROM public.documents
  WHERE (documents.user_id = auth.uid()))));


--
-- Name: processing_logs 管理员可以查看所有处理日志; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "管理员可以查看所有处理日志" ON public.processing_logs USING (((((auth.jwt() -> 'app_metadata'::text) ->> 'is_admin'::text))::boolean = true));


--
-- PostgreSQL database dump complete
--




-- GoTrue creates auth.users before this baseline is normally run. Recreate the
-- NeoFlow profile trigger when that table is available.
DO $$
BEGIN
    IF to_regclass('auth.users') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
        CREATE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users
            FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;
GRANT EXECUTE ON FUNCTION auth.role() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.jwt() TO anon, authenticated, service_role;

SELECT 'baseline: final public schema and auth compatibility ready' AS message;
