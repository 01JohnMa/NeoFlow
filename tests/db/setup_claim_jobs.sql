-- 并发认领用例前置：1 个租户 + 30 个 queued parse Job
DO $$
DECLARE
  v_tenant uuid;
  v_index int;
BEGIN
  INSERT INTO tenants(name) VALUES ('claim-gate') RETURNING id INTO v_tenant;
  FOR v_index IN 1..30 LOOP
    INSERT INTO processing_jobs (job_id, job_type, status, stage, progress, document_ids, tenant_id)
    VALUES (gen_random_uuid(), 'parse', 'queued', 'queued', 0, ARRAY[gen_random_uuid()], v_tenant);
  END LOOP;
END $$;
