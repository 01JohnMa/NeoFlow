# Page-routed evaluation (#38)

This document records the frozen preparation artifacts for the optional `page_routed` Extract strategy. The runnable manifest and rubric are in [`benchmarks/page_routed/manifest.json`](../benchmarks/page_routed/manifest.json) and [`benchmarks/page_routed/rubric.json`](../benchmarks/page_routed/rubric.json); scoring is performed by [`scripts/evaluate_page_routed.py`](../scripts/evaluate_page_routed.py).

## Preparation status

The checked-in corpus is synthetic and contains no provider output, credentials, or personal contact data. It exercises born-digital, scanned, mixed/table, exact identifiers/dates, and long-context boundary strata. It is scaffolding for deterministic scoring and must not be described as real-provider acceptance. Manifest fields for implementation commit, Configuration revision, ParseResult IDs, provider, model, and profiles remain `null` until an authorized pre-run freeze.

The runner consumes saved outcome rows (JSON array or JSONL). It scores every supplied terminal outcome, including failures, timeouts, schema/evidence-invalid outcomes, and context overflow in the denominator. Each row retains strategy, scenario (`cold_index`, `hot_index`, `first_parse`, `cross_configuration`), exact `parse_result_id`, latency, token, retry, and cache fields when supplied.

## Frozen scoring rules

Field correctness, unsupported fills, abstention, evidence-page recall, and evidence-reference validity are scored with the denominators in `rubric.json`. Gold evidence pages and allowed normalization are read before scoring; outputs never modify gold. The default fixed-corpus gate is per-stratum: no decrease in field correctness and no increase in unsupported fills versus `full_document`. No rollout latency, cost, or recall threshold is invented here; absent approved thresholds or missing provider authorization leaves expansion at **NO_GO**.

## Real-run completion checklist

Before a scored run, fill every manifest identity/profile field and each case's immutable `parse_result_id`; record source and gold hashes externally as appropriate. Run standard and page-routed strategies against the same bound ParseResult for cold/hot index, first Parse, and cross-Configuration reuse. Preserve raw terminal outcomes and provider/version/artifact references. The final report must separately identify real MinerU/embedding-provider evidence, deterministic doubles, blocked access, and any safety-gate violation. No production deployment or default migration is part of this preparation.
