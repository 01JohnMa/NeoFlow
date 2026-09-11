# tests/test_results_migration_static.py
"""022 Result 存储迁移静态检查（无需数据库）。

覆盖：results 表/索引/检查约束、RLS 与策略、processing_jobs 的
configuration_revision_id / tenant_id 幂等添加，以及不删除旧表。
"""

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
MIGRATION = MIGRATIONS_DIR / "022_results_and_job_revision.sql"


def _text() -> str:
    assert MIGRATION.exists(), "缺少 022_results_and_job_revision.sql"
    return MIGRATION.read_text(encoding="utf-8")


def test_results_table_created_idempotently_with_required_columns():
    text = _text()
    assert re.search(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+results\b", text, re.I)

    columns = [
        "tenant_id",
        "job_id",
        "document_id",
        "config_revision_id",
        "sample_key",
        "data",
        "field_meta",
        "review_state",
        "created_at",
        "updated_at",
    ]
    for column in columns:
        assert column in text, f"results 表缺少列: {column}"

    assert re.search(
        r"review_state\s+VARCHAR\(20\)[^,]*CHECK\s*\(review_state\s+IN\s*\('pending',\s*'approved',\s*'rejected'\)\)",
        text,
        re.I | re.S,
    ), "review_state 缺少取值约束"


def test_processing_jobs_adds_revision_and_tenant_idempotently():
    text = _text()
    assert re.search(
        r"ALTER\s+TABLE\s+processing_jobs\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+configuration_revision_id",
        text,
        re.I | re.S,
    ), "processing_jobs 未幂等添加 configuration_revision_id"
    assert re.search(
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+tenant_id",
        text,
        re.I,
    ), "processing_jobs 未幂等添加 tenant_id"

    assert "pg_constraint" in text, "外键添加缺少幂等判断"
    assert re.search(
        r"FOREIGN\s+KEY\s+\(configuration_revision_id\)\s+REFERENCES\s+configuration_revisions",
        text,
        re.I,
    ), "configuration_revision_id 缺少指向 configuration_revisions 的外键"


def test_results_rls_enabled_and_policies_present():
    text = _text()
    assert re.search(
        r"ALTER\s+TABLE\s+results\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", text, re.I
    ), "results 未启用 RLS"

    assert re.search(
        r'CREATE\s+POLICY\s+"Tenant members can view results"[^;]*FOR\s+SELECT[^;]*get_current_user_tenant_id',
        text,
        re.I | re.S,
    ), "results 缺少租户成员只读策略"
    assert re.search(
        r'CREATE\s+POLICY\s+"Tenant admins can manage results"[^;]*WITH\s+CHECK',
        text,
        re.I | re.S,
    ), "results 缺少管理员 WITH CHECK 策略"
    assert re.search(
        r'CREATE\s+POLICY\s+"Service role full access to results"[^;]*WITH\s+CHECK',
        text,
        re.I | re.S,
    ), "results 缺少 service_role 策略"


def test_results_indexes_created_idempotently():
    text = _text()
    for index in (
        "idx_results_tenant_created_at",
        "idx_results_job_id",
        "idx_results_document_id",
        "idx_results_config_revision_id",
    ):
        assert re.search(
            rf"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+{index}\b", text, re.I
        ), f"缺少幂等索引: {index}"


def test_migration_does_not_drop_legacy_tables():
    text = _text()
    assert not re.search(r"DROP\s+TABLE", text, re.I), "本迁移不应删除旧表"
    assert not re.search(r"ALTER\s+TABLE\s+document_templates\b", text, re.I)
