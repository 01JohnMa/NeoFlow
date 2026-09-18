# tests/test_cleanup_review_output_migration_static.py
"""025 2.0 清场迁移静态检查（无需数据库）。

覆盖：审核/输出/CRM/旧抽取入口的数据库残留删除（results / documents /
processing_jobs / feishu_push_records）、admit_parse_request 重定义后不再
写入 job_type、以及 configuration definition JSONB 中 review / output 键的清理。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
MIGRATION = MIGRATIONS_DIR / "025_cleanup_review_output_legacy.sql"

DROPPED_COLUMNS = {
    "results": ["review_state", "field_meta"],
    "documents": ["template_id", "ocr_text", "ocr_confidence", "custom_push_name"],
    "processing_jobs": ["job_type", "items", "dedupe_key"],
}

STRIPPED_DEFINITION_KEYS = [
    "extraction_mode",
    "output_mode",
    "push_attachment",
    "auto_approve",
    "feishu",
    "excel",
]

STRIPPED_FIELD_KEYS = [
    "review_enforced",
    "review_allowed_values",
    "feishu_column",
]


def _text() -> str:
    assert MIGRATION.exists(), "缺少 025_cleanup_review_output_legacy.sql"
    return MIGRATION.read_text(encoding="utf-8")


def test_legacy_columns_dropped_idempotently():
    text = _text()
    for table, columns in DROPPED_COLUMNS.items():
        for column in columns:
            assert re.search(
                rf"ALTER\s+TABLE\s+{table}\s+DROP\s+COLUMN\s+IF\s+EXISTS\s+{column}\b",
                text,
                re.I,
            ), f"025 未幂等删除 {table}.{column}"


def test_feishu_push_records_table_dropped_idempotently():
    text = _text()
    assert re.search(
        r"DROP\s+TABLE\s+IF\s+EXISTS\s+feishu_push_records\b", text, re.I
    ), "025 未幂等删除 feishu_push_records"


def test_admit_parse_request_rewritten_without_job_type():
    text = _text()
    match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+admit_parse_request\b.*?AS\s+\$\$(.*?)\$\$",
        text,
        re.I | re.S,
    )
    assert match, "025 未重定义 admit_parse_request"
    assert not re.search(r"\bjob_type\b", match.group(1), re.I), (
        "admit_parse_request 重定义仍在引用 job_type"
    )

    redefine_at = text.find("CREATE OR REPLACE FUNCTION admit_parse_request")
    drop_at = text.find("DROP COLUMN IF EXISTS job_type")
    assert 0 <= redefine_at < drop_at, (
        "admit_parse_request 必须在删除 processing_jobs.job_type 之前重定义"
    )


def test_commit_parse_job_rewritten_without_review_columns():
    text = _text()
    match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+commit_parse_job\b.*?AS\s+\$\$(.*?)\$\$",
        text,
        re.I | re.S,
    )
    assert match, "025 未重定义 commit_parse_job"
    body = match.group(1)
    assert not re.search(r"\bfield_meta\b", body, re.I), (
        "commit_parse_job 重定义仍在写入 field_meta"
    )
    assert not re.search(r"\breview_state\b", body, re.I), (
        "commit_parse_job 重定义仍在写入 review_state"
    )


def test_configuration_definition_review_and_output_keys_stripped():
    text = _text()
    assert re.search(r"UPDATE\s+configurations\b", text, re.I), (
        "025 未清洗 configurations.draft_definition"
    )
    # 历史 Revision 是触发器保护的不可变快照，不回改（读取侧忽略遗留键）
    assert not re.search(r"UPDATE\s+configuration_revisions\b", text, re.I), (
        "025 不应修改 configuration_revisions（不可变快照）"
    )

    for key in STRIPPED_DEFINITION_KEYS:
        assert re.search(rf"-\s*'{key}'", text, re.I), (
            f"025 未从 definition 移除输出键: {key}"
        )
    for key in STRIPPED_FIELD_KEYS:
        assert re.search(rf"-\s*'{key}'", text, re.I), (
            f"025 未从 fields 移除审核键: {key}"
        )

    assert re.search(r"jsonb_set\s*\(", text, re.I), "025 缺少 fields 数组重写"
    assert re.search(r"'\{fields\}'", text), "025 未定位 definition.fields"


def test_migration_only_drops_and_notifies():
    text = _text()
    assert not re.search(r"CREATE\s+TABLE", text, re.I), "清场迁移不应建表"
    assert "pg_notify" in text, "缺少 PostgREST schema 刷新通知"
