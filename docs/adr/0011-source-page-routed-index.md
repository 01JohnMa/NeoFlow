# Route source pages before canonical Parse

**Status: accepted for experiment; executable strategy pending measured acceptance**

NeoFlow's third extraction path is a source-page router. It starts from the uploaded source file, classifies each physical PDF page by usable text-layer availability, and builds a page index before creating a canonical ParseResult. Born-digital pages use their native page text for a text embedding. Scanned or unusable-text pages are rendered as images for a cross-modal image embedding. A field name and description query the matching page modality; the top two pages per field are unioned and de-duplicated. The first experiment does not fall back to a full-document Parse when no page is retrieved.

The router is generic. Its core understands physical page identity, page modality, text/image index records, field queries, candidate ranking, page-range construction, and bounded Parse/Extract execution. Document-specific structure is optional metadata supplied by a strategy profile: a profile may identify a summary region, directory anchors, section ranges, table expectations, or validation rules, but the core does not contain clinical-protocol field names or chapter numbers.

The selected page ranges are sent to one bounded Parse Job. The resulting partial Parse artifact belongs to the current Extract Job and records the source-document hash, requested physical pages, modality/index profile, Parse profile, and coverage. It never replaces the Document's canonical ParseResult and is not silently reused by another Configuration as complete input.

## Execution contract

1. Read the uploaded source and compute an immutable source hash.
2. Inspect every physical page. Use native text when it is present and usable; otherwise render that page as an image. A mixed document may contain both modalities.
3. Create or reuse page index records keyed by source hash, physical page, modality, actual input hash, embedding model/profile, and renderer/text-extractor version.
4. Build one query from each field path, field name, and description. Retrieve at most two pages per field. Union and de-duplicate page numbers. Structural profile candidates may be added; vector results are a fallback for fields without a structural route.
5. If the union is empty, leave fields unresolved. Do not infer absence and do not silently run a full Parse fallback in the first experiment.
6. Submit one `page_ranges` Parse request for the union. Bind the resulting partial artifact to this Extract Job, then run the existing schema/evidence extraction logic over the parsed pages.
7. Record candidate pages, parsed pages, partial ParseResult identity, embedding requests/cache hits, Parse requests, Extract requests, unresolved fields, and terminal outcome for comparison with `full_document`.

## Consequences

- Born-digital documents avoid full MinerU Parse before routing; source-page text extraction and embedding become the index cost.
- Scanned documents pay for page rendering and image embedding only for the source-page index; MinerU still provides the structured Parse for selected pages.
- Image retrieval locates candidate pages but does not prove exact field values or document absence. Evidence and final Schema validation remain the authority.
- The first experiment intentionally uses top-two retrieval without full fallback so that page recall and false negatives remain visible.
- The source-page path is independent from the existing complete-Parse `page_routed` experiment and from `progressive_parse_routed`; the three paths must not share a misleading strategy name.

## Out of scope for the first experiment

- Full-document fallback, automatic VLM upgrades, or silent reparse.
- Mutating or replacing the canonical Document ParseResult.
- Hard-coded clinical protocol field names in the generic router.
- A new public Page Index Job or Configuration Type.
- LLM vision extraction of the entire document in one request.
- Production/default enablement before paired quality and cost measurements.
