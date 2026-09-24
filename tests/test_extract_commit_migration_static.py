import re
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "028_extract_engine_required.sql"
)


def test_extract_success_requires_engine_object():
    text = MIGRATION.read_text(encoding="utf-8")

    assert re.search(
        r"IF\s+p_engine\s+IS\s+NULL\s+OR\s+jsonb_typeof\(p_engine\)\s+<>\s+'object'",
        text,
        re.IGNORECASE,
    )
    assert "CREATE OR REPLACE FUNCTION commit_extract_job" in text
    assert "GRANT EXECUTE ON FUNCTION commit_extract_job" in text


def test_extract_success_requires_parse_result_from_same_job():
    migration = MIGRATION.parent / "030_extract_parse_job_binding.sql"
    text = migration.read_text(encoding="utf-8")
    assert re.search(r"r\.sample_key\s*=\s*'parse'", text, re.IGNORECASE)
    assert re.search(r"r\.job_id\s*=\s*p_job_id", text, re.IGNORECASE)
