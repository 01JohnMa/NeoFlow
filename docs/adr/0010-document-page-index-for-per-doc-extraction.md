# Use a Document Page Index for long-document per-doc extraction

**Status: accepted**

For long-document `per_doc` Extraction, NeoFlow uses a derived **Document Page Index** with one embedding per physical page. The index is built from native page text when available, or from the existing MinerU `pipeline` OCR path for scanned and mixed documents, and is cached by source-document hash, page number, and parser profile. This source selection is an index-building detail; it does not infer or mutate the canonical Parse Mode. A field path, its `description`, and relevant enum values form the retrieval query; the router takes top candidate pages and their neighbors, then sends only those ranges to Parse. The index is an internal cached extraction artifact, not a user-submitted capability, not a canonical Parse Result, and not an Extraction Result.

The first extraction pass locks values that have page evidence and pass the JSON Schema validation. A later pass receives only unresolved field paths and cannot overwrite completed values. The model returns schema-shaped values plus internal page evidence in one call; local validation checks the evidence and stores it beside the result. A low retrieval score means that no candidate was found within the search budget, never that the document has no evidence.

## Considered Options

- **Static headings, directory terms, and hand-maintained synonyms as the primary router**: rejected — document and manufacturer terminology varies too much across `per_doc` extraction inputs.
- **Pure vector routing**: rejected — exact identifiers, dates, phone numbers, and section boundaries need page metadata, neighboring pages, and deterministic checks.
- **Introducing LlamaIndex or a dedicated vector platform in the first slice**: deferred — the Page Index contract stays backend-neutral until retrieval quality justifies the dependency and storage choice.

## Consequences

- A document reused by several Configurations can reuse its page embeddings; source and parser profile changes create a new index version.
- Scanned documents still pay for the full pipeline OCR needed to create page text; that cost is explicit and is not counted as an automatic 80–90% MinerU saving.
- One embedding per page is intentionally coarse. Dense or table-heavy pages may require a later section/chunk index only when measured recall shows the need.
- The Page Index improves routing recall and does not change ParseResult completeness or the JSON Schema contract.
