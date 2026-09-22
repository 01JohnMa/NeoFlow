# Page-routed evaluation (#38)

This document records preparation artifacts for the optional `page_routed` Extract strategy. The runnable manifest and rubric are in [`benchmarks/page_routed/manifest.json`](../benchmarks/page_routed/manifest.json) and [`benchmarks/page_routed/rubric.json`](../benchmarks/page_routed/rubric.json); scoring is performed by [`scripts/evaluate_page_routed.py`](../scripts/evaluate_page_routed.py).

## Preparation status

The checked-in corpus is synthetic and contains no provider output, credentials, or personal contact data. It exercises born-digital, scanned, mixed/table, exact identifiers/dates, and long-context boundary strata. It is scaffolding for deterministic scoring and must not be described as real-provider acceptance. Manifest fields for implementation commit, Configuration revision, ParseResult IDs, provider, model, and profiles remain `null` until an authorized pre-run freeze.

The runner consumes saved outcome rows (JSON array or JSONL). It scores every supplied terminal outcome, including failures, timeouts, schema/evidence-invalid outcomes, and context overflow in the denominator. Each row retains strategy, scenario (`cold_index`, `hot_index`, `first_parse`, `cross_configuration`), exact `parse_result_id`, latency, token, retry, and cache fields when supplied.

## Observed standard baseline (2026-09-22)

This is an informal browser baseline, not a frozen paired evaluation. It used the current `neoflow2.0` checkout and the existing clinical-protocol sample (42 pages) through the authenticated UI with the standard `full_document` strategy.

- The first run completed Parse and Extract in approximately 46 seconds end to end. MinerU produced a complete 42-page ParseResult; the Extract job used one model request.
- A second run against the same Document reused the bound ParseResult and completed in approximately 19 seconds. It did not call MinerU again and also used one model request.
- The UI displayed 26/38 returned top-level fields on the first run and 25/38 on the reuse run. Against the checked-in case gold, each run had 17/28 exact matches, 8 non-empty mismatches, and 3 gold fields missing. These are literal comparisons, not eight proven factual errors: wording differences and the legacy gold's month-to-day date assumptions require separate adjudication. Returned-field count is coverage, not accuracy.
- The final Extract result was readable in the browser. The only observed console errors were the expected polling 404s before ParseResult/ExtractResult became available; the terminal result request returned 200.

At the time of those baseline runs, the embedding provider was not configured and advanced execution was disabled. These measurements establish only the standard baseline, not a routing speed or quality improvement.

## Provider connection and first advanced attempt (2026-09-22)

An authorized test key was configured locally for `qwen3.7-text-embedding` on the Beijing DashScope OpenAI-compatible endpoint. A synthetic-text request returned HTTP 200, one embedding, and the requested 1024 dimensions. Credentials remain outside Git. This proves connectivity and the single-input response format, not document retrieval quality or full acceptance.

The first browser-submitted advanced Job (`e57d79d2-8e6b-4d09-b0d6-89fa0bd27678`) bound the same complete ParseResult as the baseline (`78c6ab37-6b10-4ef9-afbf-c368c8256dd6`). It failed before indexing because the test database lacked `document_page_embeddings` (`PGRST205`). The temporary `test` Configuration draft was restored and verified against its saved original. This failed attempt stays in the operational record; it supplies no extraction-quality measurement. Test-database migration authorization and a successful full rerun remain required.

After migration 029 was applied to the authorized test project, a second browser run (`3ee6350d-df61-428b-ade1-d36771425161`) completed successfully. It reused the same ParseResult, cached all 42 page vectors at 1024 dimensions, selected 20 pages, performed two semantic passes, recorded evidence for 22 fields, and consumed 58 persisted request units. The worker interval from claim at 11:57:38 to completion at 12:01:51 was approximately 253 seconds; no MinerU Parse call was made. The UI displayed 22/38 returned fields. Against the same checked-in gold, it had 16/28 exact matches, 6 non-empty mismatches, and 6 missing gold fields. The full-document baseline had 17/28 exact matches, 8 mismatches, and 3 missing fields. This reduced non-empty mismatches but did not improve exact-field count or coverage, and was materially slower in this run; it is a real **NO_GO for rollout and tuning-required result**, not proof of a quality improvement.

A hot-index rerun (`8a2034df-c009-4ee1-ac24-b77c292f1a8a`) reused those 42 cached vectors but produced the same 22/38 result, 22 evidence fields, 58 requests, and 20 selected pages. Its worker interval was approximately 238 seconds. The small cache saving did not materially change end-to-end latency; query embedding and semantic extraction dominated this sample.

The adapter now splits page requests according to `EMBEDDING_MAX_BATCH_SIZE` (20 for this model), debits the Job request budget for each batch, sends the selected dimension, and validates item indices and vector values before caching. Its OpenAI-compatible path supports plain dense embeddings. Nonempty query/document instruction settings fail explicitly with `embedding_profile_unsupported`: DashScope's `instruct`/`text_type` require its native API, as documented in the [provider guide](https://help.aliyun.com/en/model-studio/embedding). They are not silently ignored or presented as enabled.

Release remains **NO_GO / acceptance incomplete** pending the paired evaluation and its required gates. Production/default settings are unchanged.

## Frozen scoring rules

Field correctness, unsupported fills, abstention, evidence-page recall, and evidence-reference validity are scored with the denominators in `rubric.json`. Gold evidence pages and allowed normalization are read before scoring; outputs never modify gold. The default fixed-corpus gate is per-stratum: no decrease in field correctness and no increase in unsupported fills versus `full_document`. No rollout latency, cost, or recall threshold is invented here; absent approved thresholds or missing provider authorization leaves expansion at **NO_GO**.

## Real-run completion checklist

Before a scored run, fill every manifest identity/profile field and each case's immutable `parse_result_id`; record source and gold hashes externally as appropriate. Run standard and page-routed strategies against the same bound ParseResult for cold/hot index, first Parse, and cross-Configuration reuse. Preserve raw terminal outcomes and provider/version/artifact references. The final report must separately identify real MinerU/embedding-provider evidence, deterministic doubles, blocked access, and any safety-gate violation. No production deployment or default migration is part of this preparation.
