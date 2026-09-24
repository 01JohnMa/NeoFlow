#!/bin/sh
# 隔离数据库门禁（PR2b）：在临时 PostgreSQL 15 实例上验证迁移与并发不变量。
#
# 用法：
#   sh tests/db/run.sh
#
# 说明：
# - 只依赖本机 PostgreSQL 15 工具（initdb / pg_ctl / psql / createdb），
#   兼容 Homebrew postgresql@15 与 Debian/Ubuntu 路径；
# - 使用 TMPDIR 下的独立数据目录与端口（默认 55433），退出时自动销毁；
# - 不连接任何现有数据库；不读取 .env。
#
# 覆盖：
#   1. 迁移 024、026、027、028 在最小前置 schema 上的完整执行
#   2. 受理：幂等重放、键冲突、活动复用（含别名映射）、重叠冲突、
#      权限隐藏、文件数/活动 Job 上限
#   3. 交卷：认领令牌校验、幂等确认、规范产物唯一索引、失败终态
#   4. 删除守卫：活动占用冲突、完成后删除
#   5. 并发认领不变量：30 个 Job 被两个 worker 并发认领，恰好各一次
#
# 接受的残差（2026-09）：不开"交卷持锁期间不可重领"的双连接暂停用例——
# 它验证的是 PostgreSQL 原生 FOR UPDATE / SKIP LOCKED 语义，残余场景限于
# 多副本 worker + 超长网络分区。worker 副本 >1 或租约阈值调低时升级为必测。

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
GATE_DIR="${TMPDIR:-/tmp}/neoflow-db-gate"
PORT="${NF_DB_GATE_PORT:-55433}"
DB_NAME="nf_gate"

find_pg_bin() {
    if command -v initdb >/dev/null 2>&1; then
        dirname "$(command -v initdb)"
        return
    fi
    for candidate in \
        /opt/homebrew/opt/postgresql@15/bin \
        /usr/lib/postgresql/15/bin \
        /usr/local/opt/postgresql@15/bin; do
        if [ -x "$candidate/initdb" ]; then
            echo "$candidate"
            return
        fi
    done
    echo ""
}

PG_BIN=$(find_pg_bin)
if [ -z "$PG_BIN" ]; then
    echo "未找到 PostgreSQL 15 工具（initdb/pg_ctl/psql）；请先安装 postgresql@15" >&2
    exit 1
fi
export PATH="$PG_BIN:$PATH"

cleanup() {
    if [ -d "$GATE_DIR/data" ]; then
        pg_ctl -D "$GATE_DIR/data" -m immediate stop >/dev/null 2>&1 || true
    fi
    rm -rf "$GATE_DIR"
}
trap cleanup EXIT INT TERM

rm -rf "$GATE_DIR"
mkdir -p "$GATE_DIR"

echo "[gate] 初始化临时实例: $GATE_DIR (port $PORT)"
initdb -D "$GATE_DIR/data" -U postgres --auth=trust --locale=C >/dev/null
pg_ctl -D "$GATE_DIR/data" \
    -o "-p $PORT -k $GATE_DIR -c listen_addresses=" \
    -l "$GATE_DIR/pg.log" start >/dev/null
createdb -h "$GATE_DIR" -p "$PORT" -U postgres "$DB_NAME"

psql_gate() {
    psql -h "$GATE_DIR" -p "$PORT" -U postgres -d "$DB_NAME" -v ON_ERROR_STOP=1 -q "$@"
}

echo "[gate] 应用最小前置 schema"
psql_gate -f "$ROOT/tests/db/bootstrap_min.sql" >/dev/null

echo "[gate] 应用迁移 024"
psql_gate -f "$ROOT/supabase/migrations/024_parse_requests_and_admission.sql" >/dev/null

echo "[gate] 应用 Extract 迁移 026-028, 030"
psql_gate -f "$ROOT/supabase/migrations/026_extract_execution.sql" >/dev/null
psql_gate -f "$ROOT/supabase/migrations/027_extract_commit_hardening.sql" >/dev/null
psql_gate -f "$ROOT/supabase/migrations/028_extract_engine_required.sql" >/dev/null
psql_gate -f "$ROOT/supabase/migrations/030_extract_parse_job_binding.sql" >/dev/null

echo "[gate] 受理/交卷/删除冒烟"
psql_gate -f "$ROOT/tests/db/test_parse_admission.sql"

echo "[gate] Extract 预算/交卷契约冒烟"
psql_gate -f "$ROOT/tests/db/test_extract_commit.sql"

echo "[gate] 并发认领不变量"
psql_gate -f "$ROOT/tests/db/setup_claim_jobs.sql"
psql_gate -c "DO \$\$ BEGIN FOR i IN 1..40 LOOP PERFORM 1 FROM claim_next_processing_job('gate-worker-a', 1800); END LOOP; END \$\$;" &
CLAIM_A=$!
psql_gate -c "DO \$\$ BEGIN FOR i IN 1..40 LOOP PERFORM 1 FROM claim_next_processing_job('gate-worker-b', 1800); END LOOP; END \$\$;" &
CLAIM_B=$!
wait "$CLAIM_A"
wait "$CLAIM_B"
psql_gate -f "$ROOT/tests/db/verify_claim_concurrency.sql"

echo "[gate] DB GATE PASS"
