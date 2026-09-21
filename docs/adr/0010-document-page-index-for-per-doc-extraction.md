# Make page-routed extraction an optional per-doc strategy

**Status: accepted**

NeoFlow keeps `full_document` as the default Extract strategy so existing Configurations retain their current whole-ParseResult behavior. An optional `page_routed` strategy is available for long-document `per_doc` Extraction. Its Document Page Index is built from one complete, immutable canonical Parse Result in the first slice, with one embedding per physical page, and is cached by source-document hash, page number, text profile, and embedding profile. Native-text/OCR pre-indexing and cross-round incremental Parse are separate future decisions; they do not change the canonical Parse Mode in this decision.

A field path, its `description`, and relevant enum values form the retrieval query. Page-routed extraction unions vector candidates with independent lexical/structural candidates, expands physical neighbors within budget, and selects pages from the same bound Parse Result before the LLM call. The index is an internal cached extraction artifact, not a user-submitted capability, not a canonical Parse Result, and not an Extraction Result.

The `full_document` strategy keeps the current single-pass behavior. The `page_routed` strategy's first extraction pass locks values that have page evidence and pass the JSON Schema validation. A later pass receives only unresolved field paths and cannot overwrite completed values. The model returns schema-shaped values plus internal page evidence in one call; local validation checks the evidence and stores it beside the result. A low retrieval score means that no candidate was found within the search budget, never that the document has no evidence.

## Considered Options

- **Static headings, directory terms, and hand-maintained synonyms as the primary router**: rejected — document and manufacturer terminology varies too much across `per_doc` extraction inputs.
- **Pure vector routing**: rejected — exact identifiers, dates, phone numbers, and section boundaries need page metadata, neighboring pages, and deterministic checks; page-routed retrieval uses a union of vector and independent lexical/structural candidates.
- **Introducing LlamaIndex or a dedicated vector platform in the first slice**: deferred — the Page Index contract stays backend-neutral until retrieval quality justifies the dependency and storage choice.
- **Making page-routed extraction the only strategy**: rejected — the current whole-document path is the compatibility default and remains necessary for schemas that require exhaustive enumeration or full-document synthesis.

## Consequences

- Existing Configurations default to `full_document`; a published Revision or draft Job snapshot freezes the selected `extraction_strategy`.
- `page_routed` is limited to `per_doc` in the first slice; `per_page` does not skip pages and `per_table_row` remains outside the delivered contract.
- A document reused by several Configurations can reuse its page embeddings; source, text profile, or embedding profile changes create a new index version.
- Scanned documents still pay for any full Parse needed to create the canonical input; that cost is explicit and is not counted as an automatic 80–90% MinerU saving.
- One embedding per page is intentionally coarse. Dense or table-heavy pages may require a later section/chunk index only when measured recall shows the need.
- The Page Index changes LLM context selection only; it does not change ParseResult completeness, ParseResult binding, or the JSON Schema contract.
- There is no implicit fallback from `page_routed` to `full_document`; a fallback, if later needed, must be an explicit strategy setting.
