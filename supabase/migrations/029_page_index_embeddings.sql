-- ============================================================
-- MIGRATION 029: Document Page Index cache (#36)
-- ============================================================
-- Page vectors are a derived, tenant-scoped cache. They are not ParseResult
-- rows, Extraction Results, or a new public capability.
-- ============================================================

CREATE TABLE IF NOT EXISTS document_page_embeddings (
    id                       UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id                UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id              UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    parse_result_id          UUID NOT NULL REFERENCES results(id) ON DELETE RESTRICT,
    source_document_hash     TEXT NOT NULL,
    physical_page_no         INT NOT NULL CHECK (physical_page_no > 0),
    page_state               TEXT NOT NULL CHECK (
        page_state IN ('parsed', 'blank', 'parse_failed', 'unknown', 'unencoded')
    ),
    page_source               TEXT,
    page_text                 TEXT,
    page_text_hash            TEXT,
    text_profile_hash         TEXT NOT NULL,
    embedding_profile_hash    TEXT NOT NULL,
    embedding                 JSONB,
    embedding_dimension       INT,
    error                     TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT page_embedding_state_consistency CHECK (
        (page_state = 'parsed' AND page_text IS NOT NULL AND page_text_hash IS NOT NULL)
        OR page_state <> 'parsed'
    ),
    CONSTRAINT page_embedding_vector_consistency CHECK (
        (embedding IS NULL AND embedding_dimension IS NULL)
        OR (jsonb_typeof(embedding) = 'array' AND embedding_dimension IS NOT NULL AND embedding_dimension > 0)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_page_embedding_identity
    ON document_page_embeddings (
        tenant_id,
        document_id,
        parse_result_id,
        source_document_hash,
        physical_page_no,
        text_profile_hash,
        embedding_profile_hash
    );

CREATE INDEX IF NOT EXISTS idx_page_embedding_document
    ON document_page_embeddings (tenant_id, document_id, source_document_hash, physical_page_no);

CREATE INDEX IF NOT EXISTS idx_page_embedding_parse_result
    ON document_page_embeddings (tenant_id, parse_result_id);

DROP TRIGGER IF EXISTS update_document_page_embeddings_updated_at ON document_page_embeddings;
CREATE TRIGGER update_document_page_embeddings_updated_at
    BEFORE UPDATE ON document_page_embeddings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE document_page_embeddings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON document_page_embeddings FROM anon, authenticated;
GRANT ALL ON document_page_embeddings TO service_role;

DROP POLICY IF EXISTS "Service role full access to document_page_embeddings" ON document_page_embeddings;
CREATE POLICY "Service role full access to document_page_embeddings"
    ON document_page_embeddings
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

SELECT pg_notify('pgrst', 'reload schema');
SELECT '029: Document Page Index embedding cache ready' AS message;
