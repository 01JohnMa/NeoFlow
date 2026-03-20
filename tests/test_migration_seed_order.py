"""回归测试：确保 seed 不提前依赖未来 migration 新增列。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
INIT_DATA_SQL = MIGRATIONS_DIR / "002_init_data.sql"
TARGET_TABLE_MIGRATION_SQL = MIGRATIONS_DIR / "007_add_target_table.sql"


def test_init_data_does_not_reference_target_table_before_column_exists():
    """002 seed 不应直接写 target_table，避免依赖 007 才新增的列。"""
    init_data_sql = INIT_DATA_SQL.read_text(encoding="utf-8")

    assert "target_table" not in init_data_sql


def test_target_table_backfill_stays_in_migration_007():
    """target_table 的 schema 新增与数据回填继续由 007 负责。"""
    migration_sql = TARGET_TABLE_MIGRATION_SQL.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS target_table" in migration_sql
    assert "integrating_sphere" in migration_sql
    assert "light_distribution" in migration_sql
