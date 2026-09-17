-- 024 冒烟：受理幂等/冲突/权限/上限、交卷令牌、删除守卫
DO $$
DECLARE
  v_tenant uuid;
  v_u1 uuid := gen_random_uuid();
  v_u2 uuid := gen_random_uuid();
  v_a uuid; v_b uuid; v_c uuid; v_d uuid; v_e uuid;
  v_res record;
  v_req uuid; v_jobs uuid[];
  v_spec1 jsonb := '{"capability":"parse","spec_version":"1","input_selection":{},"effective_params":{"parse_mode":"pipeline"},"policy_version":"builtin-1"}'::jsonb;
  v_spec2 jsonb := '{"capability":"parse","spec_version":"1","input_selection":{},"effective_params":{"parse_mode":"vlm"},"policy_version":"builtin-1"}'::jsonb;
  v_spec1b jsonb := '{"capability":"parse","spec_version":"1","input_selection":{},"effective_params":{"parse_mode":"pipeline"},"policy_version":"builtin-2"}'::jsonb;
  v_data jsonb := '{"pages":[{"page_no":1,"blocks":[]}],"markdown":"# ok","engine":{"model_version":"pipeline"},"warnings":[]}'::jsonb;
  v_status text;
  v_file text;
  v_count int;
BEGIN
  INSERT INTO tenants(name) VALUES ('t1') RETURNING id INTO v_tenant;
  INSERT INTO documents(tenant_id,user_id,file_path) VALUES (v_tenant,v_u1,'/tmp/a.pdf') RETURNING id INTO v_a;
  INSERT INTO documents(tenant_id,user_id,file_path) VALUES (v_tenant,v_u1,'/tmp/b.pdf') RETURNING id INTO v_b;
  INSERT INTO documents(tenant_id,user_id,file_path) VALUES (v_tenant,v_u1,'/tmp/c.pdf') RETURNING id INTO v_c;
  INSERT INTO documents(tenant_id,user_id,file_path) VALUES (v_tenant,v_u1,'/tmp/d.pdf') RETURNING id INTO v_d;
  INSERT INTO documents(tenant_id,user_id,file_path) VALUES (v_tenant,v_u1,'/tmp/e.pdf') RETURNING id INTO v_e;

  -- 1) 受理成功：2 个文档 → 2 个 Job（带 Key，便于验证幂等）
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_a,v_b], v_spec1, 'K1', 'fp1', 'builtin-1', 50, 30);
  IF v_res.out_status <> 'ok' THEN RAISE EXCEPTION 'T1 admit expected ok, got %', v_res.out_status; END IF;
  IF cardinality(v_res.out_job_ids) <> 2 THEN RAISE EXCEPTION 'T1 expected 2 jobs, got %', cardinality(v_res.out_job_ids); END IF;
  v_req := v_res.out_request_id; v_jobs := v_res.out_job_ids;

  SELECT count(*) INTO v_count FROM processing_jobs
   WHERE request_id = v_req AND execution_spec ? 'document_id' AND jsonb_typeof(execution_spec->'effective_params') = 'object';
  IF v_count <> 2 THEN RAISE EXCEPTION 'T1 execution_spec missing on jobs (%)', v_count; END IF;

  -- 2) 同 Key 同指纹 → 幂等重放，返回同一组 Job
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_a,v_b], v_spec1, 'K1', 'fp1', 'builtin-1', 50, 30);
  IF v_res.out_status <> 'reused' OR v_res.out_reason <> 'idempotent_replay' OR NOT (v_res.out_job_ids @> v_jobs AND v_res.out_job_ids <@ v_jobs) THEN
    RAISE EXCEPTION 'T2 idempotent replay failed: %/%', v_res.out_status, v_res.out_reason;
  END IF;

  -- 3) 同 Key 不同指纹 → 冲突
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_a,v_b], v_spec2, 'K1', 'fp2', 'builtin-1', 50, 30);
  IF v_res.out_status <> 'conflict' OR v_res.out_reason <> 'idempotency_key_reused_with_different_request' THEN
    RAISE EXCEPTION 'T3 expected idempotency conflict, got %/%', v_res.out_status, v_res.out_reason;
  END IF;

  -- 4) 新 Key 命中活动复用：落别名映射，且终态后重试仍可解析到原 Job
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_a,v_b], v_spec1, 'K2', 'fp1', 'builtin-1', 50, 30);
  IF v_res.out_status <> 'reused' OR v_res.out_reason <> 'active_request_reused' OR NOT (v_res.out_job_ids @> v_jobs AND v_res.out_job_ids <@ v_jobs) THEN
    RAISE EXCEPTION 'T4 active reuse failed: %/%', v_res.out_status, v_res.out_reason;
  END IF;
  SELECT count(*) INTO v_count FROM job_requests WHERE idempotency_key = 'K2' AND reused_from_request_id = v_req;
  IF v_count <> 1 THEN RAISE EXCEPTION 'T4 alias row missing'; END IF;
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_a,v_b], v_spec1, 'K2', 'fp1', 'builtin-1', 50, 30);
  IF v_res.out_status <> 'reused' OR NOT (v_res.out_job_ids @> v_jobs AND v_res.out_job_ids <@ v_jobs) THEN RAISE EXCEPTION 'T4 alias replay failed'; END IF;

  -- 4b) 同意图但冻结规格不同（策略/默认值变化）→ 不得复用
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_a,v_b], v_spec1b, 'K3', 'fp1', 'builtin-2', 50, 30);
  IF v_res.out_status <> 'conflict' THEN RAISE EXCEPTION 'T4b spec-differ reuse expected conflict, got %', v_res.out_status; END IF;

  -- 5) 部分重叠 / 子集 / 不同规格 → 409 类冲突
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_b], v_spec1, NULL, 'fp1', 'builtin-1', 50, 30);
  IF v_res.out_status <> 'conflict' THEN RAISE EXCEPTION 'T5 subset overlap expected conflict, got %', v_res.out_status; END IF;
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_a], v_spec2, NULL, 'fp2', 'builtin-1', 50, 30);
  IF v_res.out_status <> 'conflict' THEN RAISE EXCEPTION 'T5 spec-differ overlap expected conflict, got %', v_res.out_status; END IF;

  -- 6) 非所有者且非管理员 → 资源不可见（404 语义）
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u2, false, ARRAY[v_c], v_spec1, NULL, 'fp3', 'builtin-1', 50, 30);
  IF v_res.out_status <> 'not_found' THEN RAISE EXCEPTION 'T6 expected not_found, got %', v_res.out_status; END IF;

  -- 7) 上限：单次文件数与活动 Job 数
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_c,v_d], v_spec1, NULL, 'fp4', 'builtin-1', 1, 30);
  IF v_res.out_status <> 'limit_exceeded' OR v_res.out_reason <> 'max_files_per_request' THEN
    RAISE EXCEPTION 'T7 max_files expected, got %/%', v_res.out_status, v_res.out_reason;
  END IF;
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_c], v_spec1, NULL, 'fp5', 'builtin-1', 50, 2);
  IF v_res.out_status <> 'limit_exceeded' OR v_res.out_reason <> 'max_active_jobs_per_tenant' THEN
    RAISE EXCEPTION 'T7 max_active expected, got %/%', v_res.out_status, v_res.out_reason;
  END IF;

  -- 8) 交卷：认领令牌校验 + 幂等确认
  UPDATE processing_jobs SET status='processing', stage='parsing', locked_by='w1', locked_at=now(), attempts=1 WHERE job_id = v_jobs[1];
  SELECT out_status INTO v_status FROM commit_parse_job(v_jobs[1], 'w2', 1, 'ok', NULL, v_data);
  IF v_status <> 'stale_token' THEN RAISE EXCEPTION 'T8 wrong worker expected stale_token, got %', v_status; END IF;
  SELECT out_status INTO v_status FROM commit_parse_job(v_jobs[1], 'w1', 0, 'ok', NULL, v_data);
  IF v_status <> 'stale_token' THEN RAISE EXCEPTION 'T8 wrong attempt expected stale_token, got %', v_status; END IF;
  SELECT out_status INTO v_status FROM commit_parse_job(v_jobs[1], 'w1', 1, 'ok', NULL, v_data);
  IF v_status <> 'completed' THEN RAISE EXCEPTION 'T8 commit expected completed, got %', v_status; END IF;
  SELECT count(*) INTO v_count FROM results WHERE job_id = v_jobs[1] AND sample_key = 'parse';
  IF v_count <> 1 THEN RAISE EXCEPTION 'T8 canonical result missing'; END IF;
  SELECT out_status INTO v_status FROM commit_parse_job(v_jobs[1], 'w1', 1, 'ok', NULL, v_data);
  IF v_status <> 'already_committed' THEN RAISE EXCEPTION 'T8 replay expected already_committed, got %', v_status; END IF;

  -- 规范产物唯一索引兜底
  BEGIN
    INSERT INTO results (tenant_id, job_id, sample_key, data) VALUES (v_tenant, v_jobs[1], 'parse', '{}'::jsonb);
    RAISE EXCEPTION 'T8 unique index did not fire';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;

  -- 9) 失败交卷 + 删除守卫
  UPDATE processing_jobs SET status='processing', stage='parsing', locked_by='w1', locked_at=now(), attempts=1 WHERE job_id = v_jobs[2];
  SELECT out_status INTO v_status FROM commit_parse_job(v_jobs[2], 'w1', 1, 'failed', 'mineru timeout', NULL);
  IF v_status <> 'failed' THEN RAISE EXCEPTION 'T9 failed commit expected failed, got %', v_status; END IF;

  SELECT out_status, out_file_path INTO v_status, v_file FROM delete_document_guarded(v_a, v_u1, false);
  IF v_status <> 'ok' OR v_file <> '/tmp/a.pdf' THEN RAISE EXCEPTION 'T9 delete expected ok, got %/%', v_status, v_file; END IF;
  SELECT count(*) INTO v_count FROM documents WHERE id = v_a;
  IF v_count <> 0 THEN RAISE EXCEPTION 'T9 document not deleted'; END IF;

  -- 活动 Job 占用时拒绝删除
  SELECT * INTO v_res FROM admit_parse_request(v_tenant, v_u1, false, ARRAY[v_e], v_spec1, NULL, 'fp6', 'builtin-1', 50, 30);
  IF v_res.out_status <> 'ok' THEN RAISE EXCEPTION 'T9 admit E failed: %', v_res.out_status; END IF;
  SELECT out_status INTO v_status FROM delete_document_guarded(v_e, v_u1, false);
  IF v_status <> 'conflict' THEN RAISE EXCEPTION 'T9 delete active expected conflict, got %', v_status; END IF;
  UPDATE processing_jobs SET status='processing', locked_by='w9', attempts=1 WHERE job_id = (SELECT job_id FROM processing_jobs WHERE document_ids @> ARRAY[v_e]);
  SELECT out_status INTO v_status FROM commit_parse_job((SELECT job_id FROM processing_jobs WHERE document_ids @> ARRAY[v_e]), 'w9', 1, 'ok', NULL, v_data);
  IF v_status <> 'completed' THEN RAISE EXCEPTION 'T9 commit E failed: %', v_status; END IF;
  SELECT out_status INTO v_status FROM delete_document_guarded(v_e, v_u1, false);
  IF v_status <> 'ok' THEN RAISE EXCEPTION 'T9 delete E after commit expected ok, got %', v_status; END IF;

  RAISE NOTICE 'SMOKE OK: 024 受理/交卷/删除 全部通过';
END $$;
