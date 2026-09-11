#!/bin/sh
# ============================================================
# 数据库首次初始化引导脚本
# ============================================================
# 仅在 db 容器 data 目录为空时，由 docker-entrypoint-initdb.d 执行。
# 作用：
#   1) 执行基础结构 supabase/migrations/000_init.sql（角色/Schema/基础表/RLS）
#   2) 用 POSTGRES_PASSWORD 设置数据库角色密码
#      （纯 SQL 无法读取 compose 环境变量，因此密码设置放在本脚本）
#
# 增量迁移（001+）不在这里执行：003_post_auth_setup.sql 依赖 auth 服务。
# 由 migrations 容器在 db/auth 就绪后通过 run_migrations.sh 应用并记录。
# ============================================================
set -e

MIGRATIONS_DIR="${MIGRATIONS_DIR:-/migrations}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-postgres}"

if [ ! -f "$MIGRATIONS_DIR/000_init.sql" ]; then
    echo "[initdb] 找不到 $MIGRATIONS_DIR/000_init.sql，无法完成初始化" >&2
    exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$DB_USER" --dbname "$DB_NAME" \
    -f "$MIGRATIONS_DIR/000_init.sql"

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "[initdb] POSTGRES_PASSWORD 未设置，无法初始化数据库角色密码" >&2
    exit 1
fi

# 密码通过 psql 变量传入，由 psql 负责安全转义，不拼接进 SQL 字符串。
psql -v ON_ERROR_STOP=1 --username "$DB_USER" --dbname "$DB_NAME" \
    -v role_password="$POSTGRES_PASSWORD" <<'SQL'
ALTER ROLE supabase_auth_admin WITH PASSWORD :'role_password';
ALTER ROLE supabase_storage_admin WITH PASSWORD :'role_password';
ALTER ROLE authenticator WITH PASSWORD :'role_password';
ALTER ROLE supabase_admin WITH PASSWORD :'role_password';
SQL

echo "[initdb] 基础结构与数据库角色密码初始化完成"
