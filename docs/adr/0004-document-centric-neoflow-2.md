# Keep NeoFlow 2.0 document-centric and defer business sample semantics

**Status: accepted**

NeoFlow 2.0 treats a Document, its Configuration Revision, its Processing Job, and its Result as the stable unit of processing. It does not define or implement business-level samples, per-page-as-sample rules, sample fan-out, sample alignment, or sample-specific review behavior; those concerns were a design mistake for the generic platform and are deferred until a separate business context supplies an explicit contract. Parse, Extract, Classify, Split, and future orchestration must preserve document/page/block provenance and use the shared Job/Revision/Result contracts without adding sample assumptions. Existing sample-shaped storage fields may remain only as a compatibility boundary until a separately authorized migration removes them.

The pipeline remains optional and composable: a single capability and a multi-step pipeline share the same persisted contracts, while Extraction consumes ParseResult as its only document input. Any future multi-document or business-specific composition must enter through an explicitly scoped adapter or a new decision, not through the core routes, workers, or generic Result semantics.
