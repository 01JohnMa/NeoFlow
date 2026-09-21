-- 029 页向量缓存：最小持久化/约束/清理冒烟。
DO $$
DECLARE
  v_tenant uuid;
  v_document uuid;
  v_parse uuid;
  v_count int;
BEGIN
  INSERT INTO tenants(name) VALUES ('page-index-gate') RETURNING id INTO v_tenant;
  INSERT INTO documents(tenant_id, user_id, file_path)
  VALUES (v_tenant, gen_random_uuid(), '/tmp/page-index-gate.pdf')
  RETURNING id INTO v_document;
  INSERT INTO results(tenant_id, document_id, sample_key, data)
  VALUES (
    v_tenant,
    v_document,
    'parse',
    '{"pages":[{"page_no":1,"markdown":"摘要"}],"engine":{"coverage":{"status":"complete"}}}'::jsonb
  ) RETURNING id INTO v_parse;

  INSERT INTO document_page_embeddings (
    tenant_id, document_id, parse_result_id, source_document_hash,
    physical_page_no, page_state, page_source, page_text, page_text_hash,
    text_profile_hash, embedding_profile_hash, embedding, embedding_dimension
  ) VALUES (
    v_tenant, v_document, v_parse, 'source-1',
    1, 'parsed', 'native-text', '摘要', 'text-1',
    'text-profile-1', 'embedding-profile-1', '[0.1,0.2]'::jsonb, 2
  ), (
    v_tenant, v_document, v_parse, 'source-1',
    2, 'blank', NULL, NULL, NULL,
    'text-profile-1', 'embedding-profile-1', NULL, NULL
  );

  SELECT count(*) INTO v_count
    FROM document_page_embeddings
   WHERE tenant_id = v_tenant AND document_id = v_document;
  IF v_count <> 2 THEN
    RAISE EXCEPTION 'page index round-trip expected 2 rows, got %', v_count;
  END IF;

  BEGIN
    INSERT INTO document_page_embeddings (
      tenant_id, document_id, parse_result_id, source_document_hash,
      physical_page_no, page_state, page_text, page_text_hash,
      text_profile_hash, embedding_profile_hash, embedding, embedding_dimension
    ) VALUES (
      v_tenant, v_document, v_parse, 'source-1',
      1, 'parsed', '摘要', 'text-1',
      'text-profile-1', 'embedding-profile-1', '[0.1,0.2]'::jsonb, 2
    );
    RAISE EXCEPTION 'page index identity unique constraint did not fire';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;

  BEGIN
    INSERT INTO document_page_embeddings (
      tenant_id, document_id, parse_result_id, source_document_hash,
      physical_page_no, page_state, text_profile_hash, embedding_profile_hash
    ) VALUES (
      v_tenant, v_document, v_parse, 'source-1',
      3, 'parsed', 'text-profile-1', 'embedding-profile-1'
    );
    RAISE EXCEPTION 'parsed page without text constraint did not fire';
  EXCEPTION WHEN check_violation THEN NULL;
  END;

  DELETE FROM document_page_embeddings WHERE document_id = v_document;
  DELETE FROM results WHERE id = v_parse;
  DELETE FROM documents WHERE id = v_document;
  DELETE FROM tenants WHERE id = v_tenant;

  RAISE NOTICE 'SMOKE OK: 029 Page Index cache round-trip/constraints';
END $$;
