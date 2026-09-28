# Related extraction project findings

Research date: 2026-09-26.

## LlamaCloud / LlamaExtract

LlamaIndex presents Parse and Extract as separate products. Extract accepts a file plus a JSON Schema and an `agentic` tier; the managed service owns the internal extraction orchestration. NeoFlow should copy the schema-driven product boundary, not reproduce a local Agent loop and its tool protocol.

Source: https://developers.llamaindex.ai/llamaparse/

## Docling

Docling converts a source into one structured document representation containing pages, layout items, tables, images, hierarchy, and provenance. Its converter supports page ranges and table/layout pipeline options. This supports keeping Parse as the structural authority and avoiding a second bespoke page-understanding graph.

Sources:
- https://docling-project.github.io/docling/concepts/docling_document/
- https://docling-project.github.io/docling/reference/document_converter/

## RAGFlow

RAGFlow describes ingestion as Parser → Transformer → Indexer. It combines full-text/BM25 and vector retrieval, and uses parent-child context to preserve a complete semantic unit around a precise hit. The useful NeoFlow lesson is hybrid retrieval plus context expansion; its full visual ingestion pipeline and index backend are broader than this single-document Extract task.

Source: https://ragflow.io/blog/is-data-processing-like-building-with-lego-here-is-a-detailed-explanation-of-the-ingestion-pipeline

## Consequence for NeoFlow

The simplest viable architecture is two core paths: Normal full Parse and one bounded Smart route (page text/image index → hybrid top-k → neighbor/context expansion → one Parse → one Extract). Agentic Plus should remain an external/provider adapter or an explicitly experimental path until it proves a quality gain that justifies its extra requests and state.
