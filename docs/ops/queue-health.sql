-- ============================================================
-- 队列健康巡检（queue-health）
-- ============================================================
-- 用法：
--   psql "$DATABASE_URL" -f docs/ops/queue-health.sql
--   （或 Supabase：psql "$SUPABASE_DB_URL" -f docs/ops/queue-health.sql）
--
-- 每段解决一个问题，按顺序跑：
--   1. 积压快照    —— 现在排着多少任务、最老的在等多久
--   2. 吞吐与等待  —— 过去 24h 消化了多少、平均/最大/95 分位等待与执行时长
--   3. 认领压力    —— attempts>1 的数量（租约重领信号）
--   4. 租户活跃度  —— 每租户进行中+排队 vs 受理闸门上限（默认 30）
--
-- 判读速查：
--   等待中位数持续增长（例：几天前 <5s 现在 >30s） → worker 不够，加 worker
--   等待接近 0、队列常年空                          → worker 富余，可减到 1-2
--   错误里出现 429/rate limit                        → 上游（MinerU）配额是瓶颈，
--                                                     加 worker 无用，去提上游额度
--   attempts>1 一天内多次出现                         → 任务耗时逼近租约阈值
--                                                     （DOC_WORKER_STALE_LOCK_SECONDS=1800）
--                                                     或负载尖峰，加 worker 或调大阈值
--
-- 字段口径：
--   created_at  = 入队时间；started_at = 首次被认领（心跳不刷新）
--   finished_at = 终态时间（completed/failed）；updated_at 会被心跳刷新，勿用作终态
-- ============================================================

-- 1) 积压快照：现在每种状态各多少，最老的排队任务等了多久
SELECT '1. 积压快照' AS section;

SELECT status,
       count(*)                          AS jobs,
       max(NOW() - created_at)           AS oldest_age
FROM processing_jobs
WHERE status IN ('queued', 'processing', 'pending')
GROUP BY status
ORDER BY status;

-- 2) 吞吐与等待：过去 24h 进入终态的任务
SELECT '2. 吞吐与等待（过去 24h）' AS section;

SELECT count(*)                                          AS finished_jobs,
       round(EXTRACT(EPOCH FROM avg(started_at - created_at)), 1)  AS avg_wait_sec,
       round(EXTRACT(EPOCH FROM max(started_at - created_at)), 1)  AS max_wait_sec,
       round(EXTRACT(EPOCH FROM percentile_cont(0.95) WITHIN GROUP (
           ORDER BY started_at - created_at)), 1)                AS p95_wait_sec,
       round(EXTRACT(EPOCH FROM avg(finished_at - started_at)), 1) AS avg_run_sec,
       round(EXTRACT(EPOCH FROM max(finished_at - started_at)), 1) AS max_run_sec
FROM processing_jobs
WHERE status IN ('completed', 'failed')
  AND finished_at IS NOT NULL
  AND created_at > NOW() - interval '24 hours';

-- 3) 认领压力：过去 24h 被重领过的任务（attempts>1）
SELECT '3. 认领压力（过去 24h，attempts>1）' AS section;

SELECT count(*) AS reclaimed_jobs,
       count(*) FILTER (WHERE status = 'completed') AS reclaimed_ok,
       count(*) FILTER (WHERE status = 'failed')    AS reclaimed_failed
FROM processing_jobs
WHERE attempts > 1
  AND created_at > NOW() - interval '24 hours';

-- 4) 租户活跃度：进行中 + 排队 vs 受理闸门（PARSE_MAX_ACTIVE_JOBS_PER_TENANT=30）
SELECT '4. 租户活跃度（进行中+排队 / 上限 30）' AS section;

SELECT tenant_id,
       count(*) AS active_jobs,
       count(*) > 30 AS over_admission_cap
FROM processing_jobs
WHERE status IN ('queued', 'processing')
GROUP BY tenant_id
ORDER BY active_jobs DESC;