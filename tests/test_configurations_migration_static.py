# tests/test_configurations_migration_static.py
"""021 配置领域迁移静态检查（无需数据库）。

覆盖：新表/Revision 不可变触发器/RLS 策略、旧模板数据迁移的幂等性、
以及迁移映射包含旧模板的全部关键字段。
"""

import re
from pathlib import Path

from services.configuration_service import DEFAULT_DEFINITION

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
MIGRATION = MIGRATIONS_DIR / "021_configurations.sql"


def _text() -> str:
    assert MIGRATION.exists(), "缺少 021_configurations.sql"
    return MIGRATION.read_text(encoding="utf-8")


def test_tables_created_idempotently():
    text = _text()
    for table in ("projects", "configurations", "configuration_revisions"):
        assert re.search(
            rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\b", text, re.I
        ), f"{table} 未使用 CREATE TABLE IF NOT EXISTS"


def test_rls_enabled_and_policies_present():
    text = _text()
    for table in ("projects", "configurations", "configuration_revisions"):
        assert re.search(
            rf"ALTER\s+TABLE\s+{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", text, re.I
        ), f"{table} 未启用 RLS"

    assert re.search(
        r"CREATE\s+POLICY\s+\"Tenant admins can manage configurations\"[^;]*WITH\s+CHECK",
        text,
        re.I | re.S,
    ), "configurations 缺少管理员 WITH CHECK 策略"
    assert re.search(
        r"CREATE\s+POLICY\s+\"Tenant members can view configurations\"[^;]*FOR\s+SELECT",
        text,
        re.I | re.S,
    ), "configurations 缺少成员只读策略"
    assert re.search(
        r"CREATE\s+POLICY\s+\"Tenant members can view configuration_revisions\"[^;]*FOR\s+SELECT",
        text,
        re.I | re.S,
    ), "configuration_revisions 缺少成员只读策略"
    assert re.search(
        r"CREATE\s+POLICY\s+\"Service role full access to configuration_revisions\"[^;]*WITH\s+CHECK",
        text,
        re.I | re.S,
    ), "configuration_revisions 缺少 service_role 策略"


def test_revisions_are_immutable_at_db_level():
    text = _text()
    assert "prevent_configuration_revision_update" in text
    assert re.search(
        r"BEFORE\s+UPDATE\s+ON\s+configuration_revisions", text, re.I
    ), "configuration_revisions 缺少不可变触发器"
    assert re.search(r"RAISE\s+EXCEPTION", text, re.I), "触发器未拒绝修改"


def test_data_migration_is_idempotent():
    text = _text()
    assert "build_legacy_template_definition" in text
    assert re.search(
        r"WHERE\s+NOT\s+EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+configurations\s+c\s+WHERE\s+c\.legacy_template_id\s*=\s*t\.id",
        text,
        re.I,
    ), "模板 -> 配置迁移缺少 legacy_template_id 去重"
    assert re.search(
        r"WHERE\s+c\.legacy_template_id\s+IS\s+NOT\s+NULL\s+AND\s+NOT\s+EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+configuration_revisions",
        text,
        re.I,
    ), "Revision 迁移缺少去重"
    assert re.search(r"ON\s+CONFLICT\s*\(configuration_id,\s*revision_number\)\s+DO\s+NOTHING", text, re.I)
    assert re.search(r" NOT\s+EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+projects", text, re.I)
    assert "CREATE OR REPLACE FUNCTION" in text


def test_definition_mapping_covers_legacy_template_columns():
    text = _text()
    mapped_columns = [
        "field_key",
        "field_label",
        "field_type",
        "extraction_hint",
        "feishu_column",
        "sort_order",
        "review_enforced",
        "review_allowed_values",
        "is_required",
        "default_value",
        "source_doc_type",
        "example_input",
        "example_output",
        "description",
        "is_active",
        "extraction_prompt_template",
        "extraction_mode",
        "per_page_extraction",
        "cleaner_module",
        "output_mode",
        "push_attachment",
        "auto_approve",
        "feishu_bitable_token",
        "feishu_table_id",
        "excel_template_file_name",
        "excel_template_path",
        "excel_template_placeholders",
    ]
    for column in mapped_columns:
        assert column in text, f"迁移映射缺少旧模板列: {column}"

    for key in DEFAULT_DEFINITION:
        assert f"'{key}'" in text, f"迁移 definition 缺少键: {key}"


def test_migration_does_not_drop_or_rename_legacy_tables():
    text = _text()
    assert not re.search(r"DROP\s+TABLE", text, re.I), "本迁移不应删除旧表"
    assert not re.search(r"ALTER\s+TABLE\s+document_templates\b", text, re.I)
    assert not re.search(r"ALTER\s+TABLE\s+template_fields\b", text, re.I)
    assert not re.search(r"ALTER\s+TABLE\s+template_examples\b", text, re.I)
