# Parse is a parameterized capability; extraction keeps revisioned templates

**Status: accepted**

Parse has no business template: its output is generic markdown, and its configurable surface is a small parameter set (Parse Mode today; input and processing options later). It therefore does not get a Configuration/Revision object, and the system Parse Configuration plus the run-time republishing path (`ensure_parse_revision`) are removed. A Parse Job records the parameters it ran under, a tenant-level parse policy bounds what may be requested (allowed modes, defaults, batch and concurrency limits), and job dispatch is by capability rather than by a mutable Configuration. Extraction keeps revisioned templates because a Field Schema is authored business knowledge that must be reviewed and replayed; this split is deliberate — a template where the definition carries business semantics, policy plus a parameter snapshot where it does not.

One Parse Job parses exactly one Document; a request covering several Documents creates one Job per Document plus one request record grouping them, so per-file status, failure, and provenance need no separate execution-item entity.

An **execution spec** is Job data, not a publishable object: capability and spec schema version, the immutable input identity (documents plus normalized input selection), the effective parameters after policy and default resolution, and the accepted policy version. The worker reads only the frozen effective parameters; a later policy change may refuse execution but never silently substitutes parameters. Results record observed engine information and the producing attempt; they never define submission identity.

## Considered Options

- **Pinning every Parse execution to a Configuration Revision**: rejected — it forced a template-shaped object with no business content, and its run-time republishing caused the shared-configuration races this decision removes.
- **Fully open parameters with no tenant policy**: rejected — enterprise tenants must govern which modes and backends may run and at what limits.
- **Per-user saved parse presets**: rejected earlier (ADR-0006); parameter defaults belong to tenant policy, not individual users.

## Consequences

- A Parse Job's execution identity is its recorded parameter snapshot, not a pinned Revision; the Parse Result's engine metadata observes what actually ran and is never part of the submission identity. ADR-0005's "every step Job pins one Revision" continues to apply to template-based capabilities (Extract, and future schemaed steps); parse steps bind their parameter snapshot.
- Input selection — documents and page ranges — is Job data. Page ranges never need a configuration version.
- The race class where concurrent runs mutate a shared definition cannot occur for Parse; reproducibility relies on the recorded parameters, with engine metadata as observation, so any future parse parameter must be recorded on the Job.
- The Parse console and the external parse contract accept the same parameters: one request, one Job, one parameter snapshot.
