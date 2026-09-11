# tests/test_cleanup_migration_static.py
"""023 收尾迁移静态检查（无需数据库）。

覆盖：业务结果表/旧模板表/动态 DDL 函数/旧映射函数的幂等删除，
以及应用代码中不再引用 legacy 业务表与已删除服务。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
MIGRATION = MIGRATIONS_DIR / "023_drop_legacy_business_tables.sql"

LEGACY_BUSINESS_TABLES = [
    "inspection_reports",
    "expresses",
    "sampling_forms",
    "packagings",
    "lighting_reports",
    "integrating_sphere_reports",
    "light_distribution_reports",
]

LEGACY_TEMPLATE_TABLES = [
    "document_templates",
    "template_fields",
    "template_examples",
]

LEGACY_FUNCTIONS = [
    "add_result_column",
    "rename_result_column",
    "drop_result_column",
    "get_result_table_columns",
    "build_legacy_template_definition",
]

APP_DIRS = ["api", "agents", "services", "workers", "config", "sdk", "constants"]


def _text() -> str:
    assert MIGRATION.exists(), "缺少 023_drop_legacy_business_tables.sql"
    return MIGRATION.read_text(encoding="utf-8")


def test_business_tables_dropped_idempotently():
    text = _text()
    for table in LEGACY_BUSINESS_TABLES:
        assert re.search(
            rf"DROP\s+TABLE\s+IF\s+EXISTS\s+{table}\b", text, re.I
        ), f"023 未幂等删除业务表: {table}"


def test_legacy_template_tables_dropped_idempotently():
    text = _text()
    for table in LEGACY_TEMPLATE_TABLES:
        assert re.search(
            rf"DROP\s+TABLE\s+IF\s+EXISTS\s+{table}\b", text, re.I
        ), f"023 未幂等删除旧模板表: {table}"


def test_legacy_functions_dropped_idempotently():
    text = _text()
    for function in LEGACY_FUNCTIONS:
        assert re.search(
            rf"DROP\s+FUNCTION\s+IF\s+EXISTS\s+{function}\s*\(", text, re.I
        ), f"023 未幂等删除旧函数: {function}"


def test_documents_fk_and_tenant_settings_removed():
    text = _text()
    assert re.search(
        r"ALTER\s+TABLE\s+documents\s+DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+documents_template_id_fkey",
        text,
        re.I,
    ), "023 未先移除 documents.template_id 外键"
    assert re.search(
        r"ALTER\s+TABLE\s+tenants\s+DROP\s+COLUMN\s+IF\s+EXISTS\s+settings",
        text,
        re.I,
    ), "023 未移除 paired-batch 遗留的 tenants.settings"


def test_migration_only_drops_and_notifies():
    text = _text()
    assert not re.search(r"CREATE\s+TABLE", text, re.I), "收尾迁移不应建表"
    assert not re.search(r"ALTER\s+ROLE", text, re.I)
    assert "pg_notify" in text, "缺少 PostgREST schema 刷新通知"


def test_app_code_has_no_legacy_references():
    # 说明：API 响应键 template_fields 是与前端的既有契约，不属于
    # 业务表映射/schema sync/镜像写入残留，故不在禁止列表。
    forbidden = [
        *LEGACY_BUSINESS_TABLES,
        *LEGACY_TEMPLATE_TABLES,
        "schema_sync_service",
        "import template_service",
        "services.template_service",
        "save_extraction_result",
        "resolve_table_name",
        "DOC_TYPE_TABLE_MAP",
    ]
    offenders = []
    for directory in APP_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                if needle in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {needle}")
    assert not offenders, "残留 legacy 引用:\n" + "\n".join(offenders)
