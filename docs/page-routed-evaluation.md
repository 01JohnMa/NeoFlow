# Page-routed evaluation (#38)

This document records historical comparison artifacts. `page_routed` is retired and is not an executable Configuration strategy. The current source-first contract is [`ADR-0011`](adr/0011-source-page-routed-index.md); any new comparison must use `source_page_routed` and Job-owned ParseResults.

## Three execution strategies

The evaluation separates the three product paths described in Issue #33:

1. **Normal (`full_document`) — fixed full flow.** Parse the complete document once, then send the complete Job-owned ParseResult to one extraction call. This is the compatibility baseline.
2. **Agentic (`source_page_routed`) — bounded source-page route.** Inspect the uploaded source page by page; use native text for usable born-digital pages and images for scanned pages; merge structural candidates with embedding top-two candidates, parse only the union with MinerU, then extract from that partial artifact. This is the target experiment for reducing first-time MinerU work.
3. **Agentic Plus (`agentic_source_page_routed`) — bounded adaptive workflow.** The agent may choose a bounded sequence of search and Parse actions, but every turn, Parse call, token, and wall-clock budget is hard; exceeding a limit fails the Job. Each Parse artifact is Job-private. There is no full-document fallback, silent downgrade, or unbounded retry.

Historical `page_routed` numbers below are retained only to explain earlier measurements. They must not be used as evidence for the current implementation or enabled in new jobs.

## Current Job-owned replay (2026-09-23)

Using the same 42-page clinical PDF, the same 30-field gold, the same schema, and the same provider, the formal JobRunner produced:

| strategy | job | Parse pages | embedding/Parse/LLM requests | elapsed | business-normalized quality |
| --- | --- | ---: | ---: | ---: | ---: |
| `full_document` | `8643bb21-7a33-4bca-9798-78116c9ac064` | 42 | 0 / 1 / 2 | 45.59 s | 28/30 gold fields (two optional NMPA fields absent in both gold and output) |
| `source_page_routed` | `b9d57a7d-cd50-4749-8c06-6e54be37f190` | 21 | 5 / 1 / 1 | 58.22 s | 28/30 gold fields (same two optional NMPA fields absent) |

The optimized bounded Agentic replay (`0eba0c32-747d-4b11-a4b5-d822b4f51098`) selected 24 pages, used two MinerU Parse calls, 15 total request units, and completed in approximately 94 seconds. Its deterministic score was **28/28 fields with gold values**, with no missing expected values or unsupported extras. It therefore reached the same business quality as `source_page_routed` on this sample, at higher cost and latency; the page cap and tool budgets remain explicit rather than allowing unbounded expansion.

The source-first run therefore proves Job-owned partial Parse binding, physical page restoration, and equal business-normalized quality for this replay. It reduced MinerU coverage by 50%, but was slower end to end because the provider still charged embedding requests and the selected-page MinerU request had fixed overhead. This is measurement evidence for the sample, not a universal cost or latency guarantee.

## Agentic source-page replay (2026-09-24)

The bounded `agentic_source_page_routed` strategy was run through the real JobRunner with the same PDF, schema, gold, embedding provider, DeepSeek provider, and MinerU adapter. The Agent made two search tool rounds and one Parse call, selecting 12 physical pages (`1-5,13-16,22,34-35`). The Job consumed 13 request units and completed in approximately 53.5 seconds. The deterministic scorer matched **26/28 fields with gold values**; both missing NMPA fields are intentionally absent from gold, and the remaining differences were the inclusion/exclusion list formatting/intro text. No unsupported extra field was returned.

The first attempt exposed a provider integration failure: DeepSeek thinking-mode tool calls require `reasoning_content` replay. The Agentic provider adapter now sends non-thinking mode for this optional path, so the successful Job is the relevant runtime evidence. This is a bounded strategy result, not rollout approval; the fixed source-first path remained 28/28 on the same corpus.

The earlier browser evidence compared a complete-Parse experiment on the same `parse_result_id`; it is not evidence for the current source-first path and must not be reported as incremental-Parse savings.

## Isolated source-first replay (2026-09-22)

The first source-first replay used the same 42-page clinical-protocol PDF and the seed 38-field schema. The file was born-digital: all 42 pages had usable native text, so this run intentionally exercised the text-index branch and did not render images.

- Native page-text extraction took approximately 0.62 seconds.
- Page embeddings used `qwen3.7-text-embedding`: 3 document batches took approximately 3.42 seconds; 2 batched field-query requests took approximately 1.49 seconds.
- Top-two retrieval per field produced 21 unique physical pages. The union was submitted as one MinerU `pipeline` `page_ranges` request: `1-3,6-7,13-17,22,27-29,31-37`.
- MinerU returned 21 parsed pages in approximately 26.85 seconds. The adapter restored the requested physical page numbers; without that mapping the provider's `1..21` local numbering would attach evidence to the wrong source pages.
- One evidence-aware Extract call took approximately 23.34 seconds, returned 24 accepted fields, and recorded 17,858 input tokens / 6,540 output tokens.
- Against the existing real-case gold, the isolated result had 16/28 literal exact matches, 8 non-empty mismatches, and 4 gold fields missing. This matches the best query-batched legacy `page_routed` exact count while parsing half as many pages, but total elapsed time was approximately 55.6 seconds versus the earlier full-document cold baseline of approximately 46 seconds.

This is a source-first Parse measurement, not a public strategy acceptance: it ran outside the Extract Job/Result persistence seam, used the born-digital text branch only, and did not test the scanned-image branch. The current result shows real Parse-page reduction but no speed or quality win yet; keep the source-first path experimental. This evidence does not authorize rollout or a default change.

## Unified comparison against the supplied real-case gold

The supplied [`4-真实案例-苹果酸阿莫曲坦片-填好的JSON.json`](../template/OCR训练-基本信息-药物注册类/4-真实案例-苹果酸阿莫曲坦片-填好的JSON.json) is the fact gold for every measured strategy. The comparison normalizes Unicode/full-width text, ignores whitespace and punctuation, and compares `sample_size` by its business value (`240例`); it still does not treat missing details or extra unsupported fields as exact matches.

| Run | Returned | Exact | Mismatch | Gold missing | Extra unsupported | Parse/input context |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `full_document` cold (`82629af4`) | 26 | 20/28 | 5 | 3 | 1 | complete 42-page Parse, one Extract request |
| `full_document` hot (`deadecdf`) | 25 | 20/28 | 5 | 3 | 0 | reused complete ParseResult, one Extract request |
| legacy complete-Parse `page_routed` (`b398f9e0`) | 26 | 19/28 | 6 | 3 | 1 | 39 selected pages across two passes, six requests |
| source-first `source_page_routed` replay | 24 | 19/28 | 5 | 4 | 0 | 21 source-selected pages, one Parse and one Extract |

The source-first replay is one field below the full-document baseline under the business-normalized rule, matches the legacy route, and has no extra unsupported value. `agentic` has no comparable frozen run yet and is intentionally absent from this table.

## Description-adjusted rerun (2026-09-22)

The seed schema descriptions were tightened for issuer/document details, date month-to-day normalization, project scope, group/treatment completeness, list preservation, table products, and direct evidence for research-product English names. Both current executable strategies were then rerun from the same Document and compared with the same gold:

| Run | Job | Worker time | Requests | Exact | Mismatch | Gold missing | Extra |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_document` | `abc3254c-063f-4aef-9e2c-100a19bc0aef` | 17.54s | 1 | 24/28 | 4 | 0 | 0 |
| legacy `page_routed` | `686c2215-00b4-42ff-9610-95ecdbf3d124` | 98.56s | 6 | 20/28 | 6 | 2 | 0 |

The description changes improved the full-document run from 20/28 to 24/28: both dates, project scope, control products, and protocol-version normalization are now present. Remaining full-document differences are `nmpa_info`, `exclusion_criteria`, `study_group`, and `secondary_endpoint`; these require normalization or structured/list extraction rather than more page routing. The legacy route improved to 20/28 but still misses both dates despite its 37-page selection, which points to its staged unresolved/field handling and date normalization path.

## NMPA schema split rerun (2026-09-23)

After replacing the single `nmpa_info` field with `nmpa_acceptance_no`, `nmpa_document_no`, and `nmpa_date`, a real `full_document` Job (`3bf32fca-34ce-4897-aaea-8e925031d6d6`) completed in 33.26 seconds with one Extract request. It returned `nmpa_document_no=2014L00847`; the sample had no direct evidence for an acceptance number or NMPA date, so those fields remained absent as required. Against the same business-normalized gold, the result was **25/28 exact, 3 mismatches, 0 missing, 0 extra**. The remaining mismatches are `exclusion_criteria`, `study_group`, and `secondary_endpoint`.

After correcting the gold exclusion item and narrowing `study_group`/`secondary_endpoint` descriptions, the follow-up Job (`43a1ac10-5b94-4c9b-be60-5334a5cf22a7`) completed in 17.56 seconds with one Extract request and reached **27/28 exact, 1 mismatch, 0 missing, 0 extra**. The only remaining difference is wording granularity in `secondary_endpoint`; all seven factual items are present.

The later gold audit found that the previous `secondary_endpoint` gold had removed the definitions from items 1, 2, and 4 and changed item 7 from “发作后” to “发作时”; that was a gold defect, not a model defect. The gold also omitted the original introductory sentences for the inclusion and exclusion criteria. After restoring those source passages, the same completed Job (`1d094e1e-3bf5-435b-9af1-8ef99f13fb4d`) scores **28/28 exact, 0 mismatch, 0 missing, 0 extra** under the business-normalized comparison. The remaining 43a1 result is retained as evidence of the earlier over-constrained description and is not the final quality result.

## Final source-first replay (2026-09-23)

The source-first replay was rerun with the final split NMPA schema and corrected gold. It indexed all 42 born-digital pages from native text, selected 23 pages, and submitted one physical-page `page_ranges` Parse: `1-4,6-7,13-17,22,26-29,31-37`.

- Native text read: 0.69s; document embeddings: 2.35s; field-query embeddings: 1.42s.
- MinerU selected-page Parse: 17.17s; Extract: 8.84s; 15,127 input tokens / 2,615 output tokens.
- Result against the corrected criteria-item gold: **27/28 exact, 1 mismatch, 0 missing, 0 extra**.
- `inclusion_criteria` and `exclusion_criteria` contain all 7/17 numbered items. Their section-introduction sentences are not field values under the schema contract and are not counted as missing.
- The remaining field is `study_objective`: the selected page contains the objective, but the one-pass source-first prompt did not combine the sponsor name from the adjacent summary-table row.

This is still an isolated source-first replay rather than a public Configuration strategy. It reduces parsed pages from 42 to 23, but its quality remains below the latest full-document 28/28 result.

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

After batching field queries by provider batch size, the final browser run (`acf3c792-1502-424e-b88e-0edc93ce83f2`) consumed 7 requests and completed in approximately 146 seconds, with 24/38 returned fields, 24 evidence fields, and the same 20 selected pages. Against gold it had 16/28 exact matches, 8 non-empty mismatches, and 4 missing fields. Query batching was therefore partially effective for latency, but the route remains much slower than the standard hot run (about 19 seconds) and did not improve exact-field quality; rollout remains **NO_GO**.

After wiring the round-robin page-budget fix, the final verification run (`b398f9e0-6452-473a-bba1-266c33a40a8c`) selected 40 distinct pages across its two passes, including physical page 34, and returned the previously missed `project_owner_phone`. It used 6 requests and completed in approximately 118 seconds; the UI returned 26/38 fields. Literal gold comparison was 16/28 exact, 9 non-empty mismatches, and 3 missing fields. Page recall improved, but the selected-page set became almost the whole document and exact quality remained below the 17/28 standard baseline. The route remains **NO_GO** and needs a page-budget/quality policy before any rollout.

The adapter now splits page requests according to `EMBEDDING_MAX_BATCH_SIZE` (20 for this model), debits the Job request budget for each batch, sends the selected dimension, and validates item indices and vector values before caching. Its OpenAI-compatible path supports plain dense embeddings. Nonempty query/document instruction settings fail explicitly with `embedding_profile_unsupported`: DashScope's `instruct`/`text_type` require its native API, as documented in the [provider guide](https://help.aliyun.com/en/model-studio/embedding). They are not silently ignored or presented as enabled.

Release remains **NO_GO / acceptance incomplete** pending the paired evaluation and its required gates. Production/default settings are unchanged.

## Frozen scoring rules

Field correctness, unsupported fills, abstention, evidence-page recall, and evidence-reference validity are scored with the denominators in `rubric.json`. Gold evidence pages and allowed normalization are read before scoring; outputs never modify gold. The default fixed-corpus gate is per-stratum: no decrease in field correctness and no increase in unsupported fills versus `full_document`. No rollout latency, cost, or recall threshold is invented here; absent approved thresholds or missing provider authorization leaves expansion at **NO_GO**.

## Real-run completion checklist

Before a scored run, fill every manifest identity/profile field and each case's immutable `parse_result_id`; record source and gold hashes externally as appropriate. Run standard and page-routed strategies against the same bound ParseResult for cold/hot index, first Parse, and cross-Configuration reuse. Preserve raw terminal outcomes and provider/version/artifact references. The final report must separately identify real MinerU/embedding-provider evidence, deterministic doubles, blocked access, and any safety-gate violation. No production deployment or default migration is part of this preparation.
