# Parse runs as a capability Job; document-level parse state is derived

**Status: accepted (amended by ADR-0007; 2026-09 note: the review-flow and CRM-push signals referenced below were removed with the NeoFlow 2.0 cleanup, issue #31 — the decision itself is unaffected and `Document.Status` no longer tracks an extraction/review lifecycle)**

Parse is a first-class capability (ADR-0005): its in-flight state lives on the Processing Job (status `queued → processing → completed/failed`, with stage progressing through parsing and saving), and its terminal artifact is the Parse Result, persisted per Document together with the Parse Mode and parameters it ran under. Document-level parse state — parsing / parsed / failed — is a projection over those two, not a value written into `Document.Status`, because `Document.Status` tracks the extraction/review lifecycle and the business signals that depend on it (review flow, CRM push), and a re-parse after review must never clobber review state. The standalone Parse entry records its parameters on the Job rather than pinning a Configuration Revision (ADR-0007). The Parse console page is a run-and-verify surface for the capability, not a state store: page state is a URL job reference plus a local UI preference, and the only per-run strategy choice is Parse Mode.

## Considered Options

- **Writing parse states into `Document.Status`**: rejected — one cursor cannot carry two independent processes, and the field is a business signal consumed by review/CRM flows.
- **Pinning every parse run to a Configuration Revision**: rejected for Parse in ADR-0007 — parse has no business template; its parameters are recorded on the Job, while extraction keeps revisioned templates.
- **Per-user saved parse configurations**: rejected — parameter defaults belong to tenant policy, not individual users.

## Consequences

- Parse-only documents do not advance `Document.Status`; the console and external callers read parse state from the Job and the Parse Result. A derived read contract can be added where that is not enough (document lists, downstream agents) without touching the lifecycle field.
- Per-Document-Kind parse policy defaults — the enterprise shape — are the next iteration; a caller may still override explicitly, and Parse Mode stays a run choice rather than a Document property.
- Capabilities are expected to be consumed by external systems and agents through stable Job/Result contracts (external capability exposure, designed separately). Parse state being readable from those contracts — rather than from UI session state — is what makes that delivery surface possible.
