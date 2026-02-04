#!/bin/sh
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-postgres}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-your-super-secret-password}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-/migrations}"
AUTH_WAIT_SECONDS="${AUTH_WAIT_SECONDS:-300}"

export PGPASSWORD="$DB_PASSWORD"

log() {
  echo "[migrate] $*"
}

wait_for_db() {
  log "等待数据库可用..."
  until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; do
    sleep 2
  done
  log "数据库已就绪"
}

ensure_migrations_table() {
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS public.schema_migrations (
  filename TEXT PRIMARY KEY,
  checksum TEXT,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SQL
}

escape_sql() {
  echo "$1" | sed "s/'/''/g"
}

has_migration() {
  file="$1"
  esc_file=$(escape_sql "$file")
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT 1 FROM public.schema_migrations WHERE filename='${esc_file}'" 2>/dev/null | grep -q 1
}

mark_migration() {
  file="$1"
  checksum="$2"
  esc_file=$(escape_sql "$file")
  esc_checksum=$(escape_sql "$checksum")
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c \
    "INSERT INTO public.schema_migrations (filename, checksum) VALUES ('${esc_file}', '${esc_checksum}')"
}

wait_for_auth_users() {
  log "等待 auth.users 可用（最长 ${AUTH_WAIT_SECONDS}s）..."
  elapsed=0
  while [ "$elapsed" -lt "$AUTH_WAIT_SECONDS" ]; do
    exists=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc \
      "SELECT 1 FROM information_schema.tables WHERE table_schema='auth' AND table_name='users'" 2>/dev/null | tr -d '[:space:]')
    if [ "$exists" = "1" ]; then
      log "auth.users 已可用"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  log "等待 auth.users 超时，停止执行"
  return 1
}

apply_migration() {
  file="$1"
  base_name=$(basename "$file")
  # 确保使用绝对路径
  full_path="${MIGRATIONS_DIR}/${base_name}"

  if has_migration "$base_name"; then
    log "跳过已执行迁移: $base_name"
    return 0
  fi

  if [ "$base_name" = "003_post_auth_setup.sql" ]; then
    wait_for_auth_users
  fi

  if [ ! -f "$full_path" ]; then
    log "错误: 文件不存在 $full_path"
    return 1
  fi

  checksum=$(sha256sum "$full_path" | awk '{print $1}')
  log "执行迁移: $base_name"
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$full_path"
  mark_migration "$base_name" "$checksum"
  log "迁移完成: $base_name"
}

main() {
  wait_for_db
  ensure_migrations_table

  if [ ! -d "$MIGRATIONS_DIR" ]; then
    log "迁移目录不存在: $MIGRATIONS_DIR"
    exit 1
  fi

  log "迁移目录: $MIGRATIONS_DIR"
  log "SQL 文件列表:"
  ls -la "$MIGRATIONS_DIR"/*.sql 2>/dev/null || log "未找到 SQL 文件"

  # 使用 find 命令获取绝对路径，按文件名排序
  for file in $(find "$MIGRATIONS_DIR" -maxdepth 1 -name "*.sql" -type f | sort); do
    apply_migration "$file"
  done

  log "全部迁移执行完毕"
}

main
