-- 最小前置 shim：仅用于隔离验证 024 迁移（非生产脚本）
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN CREATE ROLE service_role NOLOGIN; END IF;
END $$;

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$
  SELECT COALESCE(current_setting('request.jwt.claim.role', true), 'service_role')
$$;

DROP TABLE IF EXISTS results;
DROP TABLE IF EXISTS processing_jobs;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS tenants;
DROP TABLE IF EXISTS job_requests;

CREATE TABLE tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text
);

CREATE TABLE documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenants(id),
  user_id uuid,
  file_path text
);

CREATE TABLE processing_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL UNIQUE,
  job_type varchar(50) NOT NULL DEFAULT 'batch',
  status varchar(50) NOT NULL DEFAULT 'queued',
  stage varchar(50) NOT NULL DEFAULT 'queued',
  progress int NOT NULL DEFAULT 0,
  document_ids uuid[] DEFAULT ARRAY[]::uuid[],
  error text,
  created_by uuid,
  tenant_id uuid,
  configuration_revision_id uuid,
  locked_by text,
  locked_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  attempts int NOT NULL DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  job_id uuid,
  document_id uuid,
  config_revision_id uuid,
  sample_key text NOT NULL DEFAULT 'default',
  data jsonb NOT NULL DEFAULT '{}'::jsonb,
  field_meta jsonb NOT NULL DEFAULT '{}'::jsonb,
  review_state varchar(20) NOT NULL DEFAULT 'pending',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE OR REPLACE FUNCTION claim_next_processing_job(
    p_worker_id TEXT,
    p_stale_after_seconds INT DEFAULT 1800
)
RETURNS SETOF processing_jobs AS $$
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
$$ LANGUAGE plpgsql;

SELECT 'bootstrap_min: 最小前置 schema 就绪（隔离门禁专用，非生产脚本）' AS message;
