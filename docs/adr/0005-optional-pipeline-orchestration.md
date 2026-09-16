# Model pipelines as ordered capability Jobs

**Status: accepted (amended by ADR-0007)**

NeoFlow supports both single-capability calls and optional pipelines through the same Configuration, immutable Revision, Processing Job, and Result contracts. A single-capability call creates one Job bound to its execution definition; a pipeline creates an orchestration record plus ordered step Jobs, where every step Job is independently bound to the definition it executes — a Configuration Revision for template-based capabilities, or a recorded execution spec for parameterized capabilities (ADR-0007) — and writes its own Result. This preserves the current JobRunner seam while making retries and step-level observability explicit.

## Step contracts

- A pipeline declares its steps and their order. There is no implicit `Parse → Classify → Split → Extract` chain.
- A skipped step has no Job or Result. A later step may run only when its declared input contract is satisfied; the system does not silently fall back to another input.
- Parse produces the persisted ParseResult. Classify and Split consume ParseResult and return generic, provenance-aware results. Extract consumes ParseResult as its only document input. Output adapters consume approved Extraction Results.
- Existing single-capability endpoints use the same step contracts as pipeline steps. They do not create a second implementation path.

## Revision, retry, and failure semantics

- Each template-based step Job fixes one Configuration Revision at creation time, and each parameterized capability step fixes an execution spec (ADR-0007). A retry re-executes that same definition; changing it creates a new Job or pipeline run.
- A step failure stops dependent steps. Independent steps may finish, and the orchestration reports partial success with each step's terminal state and Result.
- A pipeline is complete only when every declared step is terminal. Cancellation prevents queued steps from starting and leaves completed Results addressable.
- Job and Result identity remains document/job/revision based. The core pipeline contract has no sample, per-page-as-sample, sample-alignment, or business merge semantics.

This design follows the LlamaParse/LlamaExtract separation of asynchronous parse and extraction jobs while keeping NeoFlow's existing persistence and tenant boundaries. Any business-specific composition must be introduced through an explicit adapter or a later ADR rather than a route or worker branch.
