#!/bin/bash
# 在服务器项目根目录执行：删旧镜像、用当前目录最新代码重新构建并启动
# 使用前请先把最新代码放到当前目录（Git pull / 解压包 / rsync）
set -e

COMPOSE_FILES=(-f supabase/docker-compose.yml -f docker-compose.prod.yml)

compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

ensure_storage_base_tables() {
  echo "==> 检查 storage 基础表..."
  local exists=""
  local attempt
  local max_attempts=20

  for attempt in $(seq 1 "$max_attempts"); do
    exists="$(docker exec supabase-db psql -U postgres -d postgres -tAc "SELECT to_regclass('storage.objects') IS NOT NULL;" 2>/dev/null | tr -d '[:space:]' || true)"
    if [ "$exists" = "t" ]; then
      echo "==> storage.objects 已存在，跳过修复"
      return 0
    fi
    echo "==> 等待数据库就绪 ($attempt/$max_attempts)..."
    sleep 3
  done

  echo "==> storage.objects 缺失，自动补齐 storage 基础表..."
  docker exec -i supabase-db psql -U postgres -d postgres -v ON_ERROR_STOP=1 <<'SQL'
CREATE SCHEMA IF NOT EXISTS storage;

CREATE TABLE IF NOT EXISTS storage.buckets (
  id text PRIMARY KEY,
  name text NOT NULL UNIQUE,
  owner uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS storage.objects (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  bucket_id text REFERENCES storage.buckets(id),
  name text,
  owner uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  last_accessed_at timestamptz DEFAULT now(),
  metadata jsonb
);

ALTER TABLE storage.buckets OWNER TO supabase_storage_admin;
ALTER TABLE storage.objects OWNER TO supabase_storage_admin;
SQL

  echo "==> 重启 supabase-storage 使迁移重新执行..."
  docker restart supabase-storage >/dev/null
}

cd "$(dirname "$0")/.."
echo "==> 当前目录: $(pwd)"
echo "==> 停止容器..."
compose down
echo "==> 删除旧镜像 (neoflow-api, neoflow-web)..."
docker rmi neoflow-api neoflow-web 2>/dev/null || true
echo "==> 重新构建 (--no-cache)..."
compose build --no-cache
echo "==> 启动..."
compose up -d
ensure_storage_base_tables
echo "==> 完成。查看状态:"
compose ps
