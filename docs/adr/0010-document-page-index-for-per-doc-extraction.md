# Legacy complete-Parse page routing for per-doc extraction

**Status: accepted**

This ADR records the first, complete-ParseResult page-routing implementation. The source-first third strategy described in the current product model is defined separately in [ADR-0011](0011-source-page-routed-index.md); it must not reuse this ADR's complete-Parse input assumption.

NeoFlow separates three extraction strategies so that context reduction is not confused with reducing canonical Parse coverage:

| Strategy | Input and orchestration | Status |
| --- | --- | --- |
| `full_document` | Bind one complete canonical Parse Result and run the existing whole-document extraction flow. | Compatibility default and current baseline. |
| `page_routed` | Bind one complete canonical Parse Result, embed/index its physical pages, retrieve a bounded page union per unresolved field, then run bounded extraction passes over those pages. | Legacy comparison implementation; it only reduces LLM context. |
| `progressive_parse_routed` | Parse an initial anchor-page artifact, extract the first batch of fields, route unresolved fields, create supplementary Parse artifacts for selected ranges, and extract only the remainder. | Separate planned workflow; not accepted by the current authoring/execution enum. |
| `source_page_routed` | Index the uploaded source page by page, retrieve candidates, Parse only selected ranges, and extract from a job-local partial artifact. | Defined by ADR-0011; separate experiment and not yet in the executable enum. |

The `page_routed` Document Page Index is built from one complete, immutable canonical Parse Result in the first slice, with one embedding per physical page, and is cached by source-document hash, page number, text profile, and embedding profile. It changes only the LLM context. `progressive_parse_routed` changes Parse coverage and therefore requires an explicit parse-coverage/artifact contract; it must not be implemented by rebinding or mutating the canonical Parse Result. Native-text/OCR pre-indexing and cross-round incremental Parse remain separate decisions for that workflow.

A field path, its `description`, and relevant enum values form the retrieval query. Page-routed extraction unions vector candidates with independent lexical/structural candidates, expands physical neighbors within budget, and selects pages from the same bound Parse Result before the LLM call. The index is an internal cached extraction artifact, not a user-submitted capability, not a canonical Parse Result, and not an Extraction Result.

The `full_document` strategy keeps the current single-pass behavior. The `page_routed` strategy's first extraction pass locks values that have page evidence and pass the JSON Schema validation. A later pass receives only unresolved field paths and cannot overwrite completed values. The model returns schema-shaped values plus internal page evidence in one call; local validation checks the evidence and stores it beside the result. A low retrieval score means that no candidate was found within the search budget, never that the document has no evidence. These two strategies share the existing complete-ParseResult binding. The progressive workflow must use separate immutable parse artifacts and an input manifest so that a partial artifact is never presented as a complete canonical Parse Result.

## Considered Options

- **Static headings, directory terms, and hand-maintained synonyms as the primary router**: rejected — document and manufacturer terminology varies too much across `per_doc` extraction inputs.
- **Pure vector routing**: rejected — exact identifiers, dates, phone numbers, and section boundaries need page metadata, neighboring pages, and deterministic checks; page-routed retrieval uses a union of vector and independent lexical/structural candidates.
- **Introducing LlamaIndex or a dedicated vector platform in the first slice**: deferred — the Page Index contract stays backend-neutral until retrieval quality justifies the dependency and storage choice.
- **Making page-routed extraction the only strategy**: rejected — the current whole-document path is the compatibility default and remains necessary for schemas that require exhaustive enumeration or full-document synthesis.
- **Combining progressive Parse with page-routed retrieval under one strategy**: rejected — the former changes Parse coverage and shared-Document semantics, while the latter only selects context from an already complete Parse Result. They need different persistence, retry, and acceptance contracts.

## Consequences

- Existing Configurations default to `full_document`; a published Revision or draft Job snapshot freezes the selected `extraction_strategy`.
- `page_routed` is limited to `per_doc` in the first slice; `per_page` does not skip pages and `per_table_row` remains outside the delivered contract.
- `progressive_parse_routed` is not a current executable strategy. It must not be accepted by the current Configuration validator until parse artifacts, coverage, merge/read rules, and retry semantics have their own implementation and acceptance ticket.
- A document reused by several Configurations can reuse its page embeddings; source, text profile, or embedding profile changes create a new index version.
- Scanned documents still pay for any full Parse needed to create the canonical input; that cost is explicit and is not counted as an automatic 80–90% MinerU saving.
- One embedding per page is intentionally coarse. Dense or table-heavy pages may require a later section/chunk index only when measured recall shows the need.
- The Page Index changes LLM context selection only; it does not change ParseResult completeness, ParseResult binding, or the JSON Schema contract.
- A progressive Parse workflow may create additional immutable partial artifacts, but it cannot mutate an existing canonical Parse Result or make a partial artifact appear complete to other Configurations.
- There is no implicit fallback from `page_routed` to `full_document`; a fallback, if later needed, must be an explicit strategy setting.
