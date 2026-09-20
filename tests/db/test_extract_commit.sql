-- 026-028 Extract 冒烟：预算、认领令牌、engine 必填、数组结果和幂等交卷。
DO $$
DECLARE
  v_tenant uuid;
  v_user uuid := gen_random_uuid();
  v_document uuid;
  v_parse_result uuid;
  v_job uuid := gen_random_uuid();
  v_stale_job uuid := gen_random_uuid();
  v_status text;
  v_reason text;
  v_count int;
  v_engine jsonb := '{"name":"test-engine"}'::jsonb;
BEGIN
  INSERT INTO tenants(name) VALUES ('extract-gate') RETURNING id INTO v_tenant;
  INSERT INTO documents(tenant_id, user_id, file_path)
  VALUES (v_tenant, v_user, '/tmp/extract-gate.pdf')
  RETURNING id INTO v_document;
  INSERT INTO results(tenant_id, job_id, document_id, sample_key, data, engine)
  VALUES (
    v_tenant,
    gen_random_uuid(),
    v_document,
    'parse',
    '{"markdown":"source","pages":[]}'::jsonb,
    '{"name":"parse"}'::jsonb
  )
  RETURNING id INTO v_parse_result;

  INSERT INTO processing_jobs(
    job_id, status, stage, document_ids, tenant_id, locked_by, attempts,
    parse_result_id, execution_budget
  ) VALUES (
    v_job, 'processing', 'llm', ARRAY[v_document], v_tenant, 'extract-worker', 1,
    v_parse_result,
    '{"max_requests":3,"requests_used":0,"deadline":"2099-01-01T00:00:00Z"}'::jsonb
  );

  SELECT out_status, out_reason
    INTO v_status, v_reason
    FROM commit_extract_job(
      v_job, 'extract-worker', 1, 'ok', NULL, '[]'::jsonb, NULL
    );
  IF v_status <> 'invalid' OR v_reason <> 'engine_invalid' THEN
    RAISE EXCEPTION 'T1 NULL engine expected invalid/engine_invalid, got %/%', v_status, v_reason;
  END IF;

  SELECT out_status INTO v_status
    FROM commit_extract_job(
      v_job, 'extract-worker', 1, 'ok', NULL, '[]'::jsonb, v_engine
    );
  IF v_status <> 'completed' THEN
    RAISE EXCEPTION 'T2 array result expected completed, got %', v_status;
  END IF;
  SELECT count(*) INTO v_count
    FROM results
   WHERE job_id = v_job AND sample_key = 'extract'
     AND data = '[]'::jsonb AND engine = v_engine;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'T2 extract result round-trip failed';
  END IF;

  SELECT out_status INTO v_status
    FROM commit_extract_job(
      v_job, 'extract-worker', 1, 'ok', NULL, '{"retry":true}'::jsonb, v_engine
    );
  IF v_status <> 'already_committed' THEN
    RAISE EXCEPTION 'T3 replay expected already_committed, got %', v_status;
  END IF;

  INSERT INTO processing_jobs(
    job_id, status, stage, document_ids, tenant_id, locked_by, attempts,
    parse_result_id, execution_budget
  ) VALUES (
    v_stale_job, 'processing', 'llm', ARRAY[v_document], v_tenant, 'new-worker', 2,
    v_parse_result,
    '{"max_requests":3,"requests_used":0,"deadline":"2099-01-01T00:00:00Z"}'::jsonb
  );
  SELECT out_status, out_reason INTO v_status, v_reason
    FROM commit_extract_job(
      v_stale_job, 'old-worker', 1, 'ok', NULL, '{}'::jsonb, v_engine
    );
  IF v_status <> 'stale_token' OR v_reason <> 'claim_ownership_lost' THEN
    RAISE EXCEPTION 'T4 stale claim expected stale_token, got %/%', v_status, v_reason;
  END IF;

  DELETE FROM processing_jobs WHERE job_id IN (v_job, v_stale_job);
  DELETE FROM results WHERE id = v_parse_result;
  DELETE FROM documents WHERE id = v_document;
  DELETE FROM tenants WHERE id = v_tenant;

  RAISE NOTICE 'SMOKE OK: 026-028 Extract budget/commit contract';
END $$;
