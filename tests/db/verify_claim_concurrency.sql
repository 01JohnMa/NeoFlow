-- 并发认领不变量：每个 Job 恰好被认领一次，全部进入 processing
DO $$
DECLARE
  v_duplicated int;
  v_processing int;
  v_workers int;
BEGIN
  SELECT count(*) INTO v_duplicated
  FROM processing_jobs j JOIN tenants t ON t.id = j.tenant_id
  WHERE t.name = 'claim-gate' AND j.attempts <> 1;
  IF v_duplicated <> 0 THEN
    RAISE EXCEPTION '并发认领重复: % 个 Job 的 attempts <> 1', v_duplicated;
  END IF;

  SELECT count(*) INTO v_processing
  FROM processing_jobs j JOIN tenants t ON t.id = j.tenant_id
  WHERE t.name = 'claim-gate' AND j.status = 'processing';
  IF v_processing <> 30 THEN
    RAISE EXCEPTION '认领数量异常: 期望 30，实际 %', v_processing;
  END IF;

  SELECT count(DISTINCT j.locked_by) INTO v_workers
  FROM processing_jobs j JOIN tenants t ON t.id = j.tenant_id
  WHERE t.name = 'claim-gate' AND j.status = 'processing' AND j.locked_by IS NOT NULL;
  IF v_workers < 1 THEN
    RAISE EXCEPTION '没有 worker 完成认领';
  END IF;

  RAISE NOTICE 'CLAIM CONCURRENCY OK: 30 个 Job 各被认领一次（% 个 worker）', v_workers;
END $$;
