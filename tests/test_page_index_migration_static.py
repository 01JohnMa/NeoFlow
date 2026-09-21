from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "029_page_index_embeddings.sql"


def test_page_index_migration_defines_tenant_scoped_cache_and_identity():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS document_page_embeddings" in text
    for column in (
        "tenant_id",
        "document_id",
        "parse_result_id",
        "source_document_hash",
        "physical_page_no",
        "page_state",
        "text_profile_hash",
        "embedding_profile_hash",
        "embedding",
    ):
        assert column in text
    assert "ALTER TABLE document_page_embeddings ENABLE ROW LEVEL SECURITY" in text
    assert "Service role full access to document_page_embeddings" in text
    assert "uq_page_embedding_identity" in text
