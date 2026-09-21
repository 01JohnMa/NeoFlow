# Page-routed evaluation (#38)

This document records the frozen preparation artifacts for the optional `page_routed` Extract strategy. The runnable manifest and rubric are in [`benchmarks/page_routed/manifest.json`](../benchmarks/page_routed/manifest.json) and [`benchmarks/page_routed/rubric.json`](../benchmarks/page_routed/rubric.json); scoring is performed by [`scripts/evaluate_page_routed.py`](../scripts/evaluate_page_routed.py).

## Preparation status

The checked-in corpus is synthetic and contains no provider output, credentials, or personal contact data. It exercises born-digital, scanned, mixed/table, exact identifiers/dates, and long-context boundary strata. It is scaffolding for deterministic scoring and must not be described as real-provider acceptance. Manifest fields for implementation commit, Configuration revision, ParseResult IDs, provider, model, and profiles remain `null` until an authorized pre-run freeze.

The runner consumes saved outcome rows (JSON array or JSONL). It scores every supplied terminal outcome, including failures, timeouts, schema/evidence-invalid outcomes, and context overflow in the denominator. Each row retains strategy, scenario (`cold_index`, `hot_index`, `first_parse`, `cross_configuration`), exact `parse_result_id`, latency, token, retry, and cache fields when supplied.

## Observed standard baseline (2026-09-22)

This is an informal browser baseline, not a frozen paired evaluation. It used the current `neoflow2.0` checkout and the existing clinical-protocol sample (42 pages) through the authenticated UI with the standard `full_document` strategy.

- The first run completed Parse and Extract in approximately 46 seconds end to end. MinerU produced a complete 42-page ParseResult; the Extract job used one model request.
- A second run against the same Document reused the bound ParseResult and completed in approximately 19 seconds. It did not call MinerU again and also used one model request.
- The UI displayed 26/38 returned top-level fields on the first run and 25/38 on the reuse run. Against the checked-in case gold, each run had 17/28 exact matches, 8 non-empty mismatches, and 3 gold fields missing. Returned-field count is coverage, not accuracy.
- The final Extract result was readable in the browser. The only observed console errors were the expected polling 404s before ParseResult/ExtractResult became available; the terminal result request returned 200.

No `page_routed` run is included here: the local embedding base URL, model, and key are not configured, and `EXTRACT_PAGE_ROUTED_ENABLED` remains false. These measurements therefore establish the standard baseline and a **NO_GO for page-routed rollout**, not a claim that routing is faster or more accurate.

## Frozen scoring rules

Field correctness, unsupported fills, abstention, evidence-page recall, and evidence-reference validity are scored with the denominators in `rubric.json`. Gold evidence pages and allowed normalization are read before scoring; outputs never modify gold. The default fixed-corpus gate is per-stratum: no decrease in field correctness and no increase in unsupported fills versus `full_document`. No rollout latency, cost, or recall threshold is invented here; absent approved thresholds or missing provider authorization leaves expansion at **NO_GO**.

## Real-run completion checklist

Before a scored run, fill every manifest identity/profile field and each case's immutable `parse_result_id`; record source and gold hashes externally as appropriate. Run standard and page-routed strategies against the same bound ParseResult for cold/hot index, first Parse, and cross-Configuration reuse. Preserve raw terminal outcomes and provider/version/artifact references. The final report must separately identify real MinerU/embedding-provider evidence, deterministic doubles, blocked access, and any safety-gate violation. No production deployment or default migration is part of this preparation.
