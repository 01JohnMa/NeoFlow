#!/bin/sh
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-postgres}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-your-super-secret-password}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-/migrations}"
AUTH_WAIT_SECONDS="${AUTH_WAIT_SECONDS:-300}"

# 固定排序规则，保证迁移顺序可预测（重复编号按文件名字典序执行）
LC_ALL=C
export LC_ALL
export PGPASSWORD="$DB_PASSWORD"

log() {
  echo "[migrate] $*"
}

# 防御：若有人仍把整个 migrations 目录挂到 docker-entrypoint-initdb.d，
# entrypoint 会 source 本脚本；此时数据库还在 initdb 临时实例上、未监听 TCP，
# 继续等待 "db" 会永久卡住初始化。直接返回，交给 migrations 容器处理。
if [ "${0##*/}" != "run_migrations.sh" ]; then
  log "检测到由 docker-entrypoint 引入执行（$0），跳过；SQL 已由 entrypoint 执行，稍后由 migrations 容器记录"
  return 0 2>/dev/null || exit 0
fi

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

-- 迁移记录表同样不应经 PostgREST 暴露给匿名/登录角色
ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.schema_migrations FROM anon, authenticated';
  END IF;
END $$;
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

recorded_checksum() {
  file="$1"
  esc_file=$(escape_sql "$file")
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT COALESCE(checksum, '') FROM public.schema_migrations WHERE filename='${esc_file}'" 2>/dev/null | tr -d '[:space:]'
}

file_checksum() {
  sha256sum "$1" | awk '{print $1}'
}

mark_migration() {
  file="$1"
  checksum="$2"
  esc_file=$(escape_sql "$file")
  esc_checksum=$(escape_sql "$checksum")
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c \
    "INSERT INTO public.schema_migrations (filename, checksum) VALUES ('${esc_file}', '${esc_checksum}')"
}

backfill_checksum() {
  file="$1"
  checksum="$2"
  esc_file=$(escape_sql "$file")
  esc_checksum=$(escape_sql "$checksum")
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c \
    "UPDATE public.schema_migrations SET checksum = '${esc_checksum}' WHERE filename = '${esc_file}'"
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

check_duplicate_numbering() {
  seen=""
  duplicates=""
  for file in $1; do
    base_name=$(basename "$file")
    number=$(printf '%s' "$base_name" | sed -n 's/^\([0-9][0-9]*\)_.*/\1/p')
    [ -n "$number" ] || continue
    case " $seen " in
      *" $number "*)
        case " $duplicates " in
          *" $number "*) ;;
          *) duplicates="$duplicates $number" ;;
        esac
        ;;
      *) seen="$seen $number" ;;
    esac
  done
  if [ -n "$duplicates" ]; then
    log "警告: 检测到重复迁移编号:$duplicates"
    log "       已按文件名字典序继续执行（顺序确定）；建议后续新增迁移使用唯一编号"
  fi
}

apply_migration() {
  file="$1"
  base_name=$(basename "$file")
  # 确保使用绝对路径
  full_path="${MIGRATIONS_DIR}/${base_name}"

  if has_migration "$base_name"; then
    if [ ! -f "$full_path" ]; then
      log "已执行迁移的本地文件不存在，保持跳过: $base_name"
      return 0
    fi

    current_checksum=$(file_checksum "$full_path")
    prior_checksum=$(recorded_checksum "$base_name")
    if [ -z "$prior_checksum" ]; then
      log "已执行迁移缺少校验和，补录: $base_name"
      backfill_checksum "$base_name" "$current_checksum"
    elif [ "$prior_checksum" != "$current_checksum" ]; then
      log "警告: 已执行迁移内容与当前文件不一致，保持跳过: $base_name"
      log "       已记录=${prior_checksum} 当前=${current_checksum}"
      log "       不会重新执行，避免产生未知状态；如有意修改请人工确认数据库现状"
    else
      log "跳过已执行迁移: $base_name"
    fi
    return 0
  fi

  if [ ! -f "$full_path" ]; then
    log "错误: 文件不存在 $full_path"
    return 1
  fi

  if [ "$base_name" = "003_post_auth_setup.sql" ]; then
    wait_for_auth_users
  fi

  checksum=$(file_checksum "$full_path")
  log "执行迁移: $base_name"
  # -1/--single-transaction: 单个迁移文件要么整体成功要么整体回滚，
  # 重复执行时不会留下半应用状态。
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -1 -f "$full_path"
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

  # 使用 find 命令获取绝对路径，按文件名排序（LC_ALL=C 固定顺序）
  migration_files=$(find "$MIGRATIONS_DIR" -maxdepth 1 -name "*.sql" -type f | sort)

  check_duplicate_numbering "$migration_files"

  for file in $migration_files; do
    apply_migration "$file"
  done

  log "全部迁移执行完毕"
}

main
