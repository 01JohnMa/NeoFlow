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
    v_job,
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

  SELECT out_status, out_reason INTO v_status, v_reason
    FROM commit_extract_job(
      v_stale_job, 'new-worker', 2, 'ok', NULL, '{}'::jsonb, v_engine
    );
  IF v_status <> 'invalid' OR v_reason <> 'binding_invalid' THEN
    RAISE EXCEPTION 'T5 cross-job ParseResult expected invalid/binding_invalid, got %/%', v_status, v_reason;
  END IF;

  DELETE FROM processing_jobs WHERE job_id IN (v_job, v_stale_job);
  DELETE FROM results WHERE id = v_parse_result;
  DELETE FROM documents WHERE id = v_document;
  DELETE FROM tenants WHERE id = v_tenant;

  RAISE NOTICE 'SMOKE OK: Extract budget/commit/job-private-Parse contract';
END $$;

-- Extract ParseResult 写入与绑定必须是同一事务，且只能绑定当前 Job。
DO $$
DECLARE
  v_tenant uuid := gen_random_uuid();
  v_document uuid := gen_random_uuid();
  v_job uuid := gen_random_uuid();
  v_status text;
  v_result uuid;
BEGIN
  INSERT INTO tenants(id, name) VALUES (v_tenant, 'parse-bind-gate');
  INSERT INTO documents(id, tenant_id, user_id, file_path)
  VALUES (v_document, v_tenant, gen_random_uuid(), '/tmp/parse-bind.pdf');
  INSERT INTO processing_jobs(job_id, status, stage, document_ids, tenant_id, locked_by,
                              attempts, execution_budget)
  VALUES (v_job, 'processing', 'parse', ARRAY[v_document], v_tenant, 'parse-worker', 1,
          '{"max_requests":3,"requests_used":0,"deadline":"2099-01-01T00:00:00Z"}'::jsonb);
  SELECT out_status, out_parse_result_id INTO v_status, v_result
  FROM commit_extract_parse_result(v_job, 'parse-worker', 1,
                                   '{"markdown":"private"}'::jsonb,
                                   '{"name":"mineru"}'::jsonb);
  IF v_status <> 'bound' OR v_result IS NULL THEN
    RAISE EXCEPTION 'atomic parse bind failed: %/%', v_status, v_result;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM processing_jobs WHERE job_id = v_job AND parse_result_id = v_result) THEN
    RAISE EXCEPTION 'parse job binding not persisted';
  END IF;
  SELECT out_status INTO v_status
  FROM commit_extract_parse_result(v_job, 'other-worker', 99,
                                   '{"markdown":"stale"}'::jsonb, '{}'::jsonb);
  IF v_status <> 'stale_token' THEN
    RAISE EXCEPTION 'stale parse worker must be rejected, got %', v_status;
  END IF;
  SELECT out_status INTO v_status
  FROM commit_extract_parse_result(v_job, 'parse-worker', 1,
                                   '{"markdown":"retry"}'::jsonb, '{}'::jsonb);
  IF v_status <> 'already_bound' THEN
    RAISE EXCEPTION 'bound job retry must be idempotent, got %', v_status;
  END IF;
END $$;
