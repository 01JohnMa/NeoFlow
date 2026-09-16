# Parse runs as a capability Job; document-level parse state is derived

**Status: accepted**

Parse is a first-class capability (ADR-0005): its in-flight state lives on the Processing Job (`queued → parsing → saving → completed/failed`), and its terminal artifact is the Parse Result, persisted per Document together with the Parse Mode and parameters it ran under. Document-level parse state — parsing / parsed / failed — is a projection over those two, not a value written into `Document.Status`, because `Document.Status` tracks the extraction/review lifecycle and the business signals that depend on it (review flow, CRM push), and a re-parse after review must never clobber review state. The standalone Parse entry pins a Parse Configuration Revision like every Job (initially the tenant's system Parse Configuration). The Parse console page is a run-and-verify surface for the capability, not a state store: page state is a URL job reference plus a local UI preference, and the only per-run choice is Parse Mode.

## Considered Options

- **Writing parse states into `Document.Status`**: rejected — one cursor cannot carry two independent processes, and the field is a business signal consumed by review/CRM flows.
- **Storing job-level parameter overrides (e.g. page ranges)**: deferred — keeps every Job fully described by its pinned Revision.
- **Per-user saved parse configurations**: rejected — enterprise processing definitions are governed at the Configuration layer; user-level state is limited to non-business UI preferences.

## Consequences

- Parse-only documents do not advance `Document.Status`; the console and external callers read parse state from the Job and the Parse Result. A derived read API can be added later where that is not enough (document lists, downstream agents) without touching the lifecycle field.
- Operators choose Parse Mode per run in this iteration. Fixed per-Document-Kind parse policy — the enterprise default — is the next iteration; until then the console is explicitly a run-choice surface, and Parse Mode is a run choice rather than a Document property.
- Capabilities are expected to be consumed by external systems and agents through stable Job/Result contracts (external capability exposure, designed separately). Parse state being readable from those contracts — rather than from UI session state — is what makes that delivery surface possible.
