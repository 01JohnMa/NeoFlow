# Route source pages before Job-owned Parse

**Status: accepted**

## Interface names

All three extraction strategies remain selectable:

| Interface name | API identifier | Execution |
|---|---|---|
| Normal | `full_document` | Parse the complete source, then extract. |
| Agentic | `source_page_routed` | Retrieve source pages, parse the selected pages, then extract. |
| Agentic Plus | `agentic_source_page_routed` | Use bounded iterative search and parsing, then extract. |

These are display names only. API identifiers, execution algorithms, and the `full_document` default remain unchanged. Agentic names the fixed source-page routing strategy; Agentic Plus names the tool-driven routing strategy.

## Decision

NeoFlow's `source_page_routed` extraction strategy starts from the uploaded source file, classifies each physical PDF page by usable text-layer availability, and builds a page index before creating a ParseResult owned by the current Extract Job. Born-digital pages use their native page text for a text embedding. Scanned or unusable-text pages are rendered as images for a cross-modal image embedding. A field name and description query the matching page modality; the top two pages per field are unioned and de-duplicated. There is no full-document fallback when no page is retrieved.

The router is generic. Its core understands physical page identity, page modality, text/image index records, field queries, candidate ranking, page-range construction, and bounded Parse/Extract execution. Document-specific structure is optional metadata supplied by a strategy profile: a profile may identify a summary region, directory anchors, section ranges, table expectations, or validation rules, but the core does not contain clinical-protocol field names or chapter numbers.

The selected page ranges are sent to one bounded Parse request within the current Extract Job. The resulting partial Parse artifact is stored as `sample_key=parse` with the current Extract Job's `job_id` and records the source-document hash, requested physical pages, modality/index profile, Parse profile, and coverage. It is retained for audit and retry, but is never silently reused by another Configuration as input. `full_document` follows the same Job-owned binding while parsing the full source.

## Execution contract

1. Read the uploaded source and compute an immutable source hash.
2. Inspect every physical page. Use native text when it is present and usable; otherwise render that page as an image. A mixed document may contain both modalities.
3. Create a Job-local page index keyed in memory by source hash, physical page, modality, actual input hash, embedding model/profile, and renderer/text-extractor version. Persistent vector-cache reuse is deferred until the source-first measurements justify it; it must not change ParseResult ownership.
4. Build one query from each field path, field name, and description. Retrieve at most two pages per field. Union and de-duplicate page numbers. Structural profile candidates may be added; vector results are a fallback for fields without a structural route.
5. If the union is empty, leave fields unresolved. Do not infer absence and do not silently run a full Parse fallback.
6. Submit one `page_ranges` Parse request for the union. Bind the resulting partial artifact to this Extract Job, then run the existing schema/evidence extraction logic over the parsed pages.
7. Record candidate pages, parsed pages, partial ParseResult identity, embedding requests, Parse requests, Extract requests, unresolved fields, and terminal outcome for comparison with `full_document`.

## Consequences

- Born-digital documents avoid full MinerU Parse before routing; source-page text extraction and embedding become the index cost.
- Scanned documents pay for page rendering and image embedding only for the source-page index; MinerU still provides the structured Parse for selected pages.
- Image retrieval locates candidate pages but does not prove exact field values or document absence. Evidence and final Schema validation remain the authority.
- The formal source-page path uses top-two retrieval without full fallback so that page recall and false negatives remain visible.
- The source-page path is independent from the retired complete-Parse `page_routed` experiment and from the separate Agentic Plus (`agentic_source_page_routed`) strategy; those names are not interchangeable.

## Out of scope for the first formal version

- Full-document fallback, automatic VLM upgrades, or silent reparse.
- Treating a Document-level latest ParseResult as an Extract input.
- Hard-coded clinical protocol field names in the generic router.
- A new public Page Index Job or Configuration Type.
- LLM vision extraction of the entire document in one request.
- Making `source_page_routed` the global default; `full_document` remains the default while paired quality and cost measurements are collected.
