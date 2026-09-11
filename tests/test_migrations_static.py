"""数据库迁移静态检查（无需数据库、无需 Docker）。

用于在无法启动 Postgres 的环境下，验证安全加固相关的迁移内容仍然存在：
硬编码角色密码、processing_jobs / feishu_push_records 的 RLS 与策略。
"""

import re
from pathlib import Path

SUPABASE_DIR = Path(__file__).resolve().parents[1] / "supabase"
MIGRATIONS_DIR = SUPABASE_DIR / "migrations"
SECURITY_MIGRATION = MIGRATIONS_DIR / "020_security_rls_hardening.sql"


def test_role_passwords_are_not_hardcoded_in_sql():
    pattern = re.compile(r"ALTER\s+ROLE\s+\S+\s+(WITH\s+)?PASSWORD\s+'", re.IGNORECASE)
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        assert not pattern.search(
            path.read_text(encoding="utf-8")
        ), f"{path.name} 仍包含硬编码角色密码"


def test_password_init_script_reads_environment():
    script = SUPABASE_DIR / "initdb" / "000_bootstrap.sh"
    assert script.exists(), "缺少 initdb/000_bootstrap.sh（fresh init 密码来源）"
    text = script.read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD" in text
    assert re.search(r"ALTER\s+ROLE\s+supabase_auth_admin\s+WITH\s+PASSWORD", text)
    assert re.search(r"ALTER\s+ROLE\s+authenticator\s+WITH\s+PASSWORD", text)


def test_compose_bootstraps_only_from_initdb_dir():
    text = (SUPABASE_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    assert "./initdb:/docker-entrypoint-initdb.d" in text
    assert "./migrations:/docker-entrypoint-initdb.d" not in text


def test_jobs_and_push_records_have_rls_enabled():
    text = SECURITY_MIGRATION.read_text(encoding="utf-8")
    for table in ("processing_jobs", "feishu_push_records"):
        assert re.search(
            rf"ALTER\s+TABLE\s+{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", text, re.I
        ), f"{table} 未启用 RLS"
        assert re.search(
            rf"CREATE\s+POLICY[^;]*ON\s+{table}[^;]*WITH\s+CHECK", text, re.I | re.S
        ), f"{table} 缺少带 WITH CHECK 的策略"


def test_profiles_update_policy_has_with_check():
    text = SECURITY_MIGRATION.read_text(encoding="utf-8")
    match = re.search(
        r'CREATE\s+POLICY\s+"Users can update own profile"\s+ON\s+profiles[^;]*;',
        text,
        re.I | re.S,
    )
    assert match, "020 未收紧 profiles 更新策略"
    assert "WITH CHECK" in match.group(0).upper()
