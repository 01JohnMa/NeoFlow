# Extract schema is a JSON Schema subset; draft runs freeze a Job-level snapshot

**Status: accepted**

Extract's schema contract is a JSON Schema subset (Draft 2020-12), stored on the Configuration definition as `data_schema`: nested objects and arrays, `enum`, `format: date`, and `description` as the extraction guidance. The previous flat Field Schema (field_key/label/type/hint plus review and output mappings) is retired: review and external outputs left NeoFlow 2.0 (#31), so its remaining jobs — nesting, enums, and machine-checkable constraints — are exactly what a schema subset does better, with no translation layer. Unsupported keywords are rejected at publish/submit time rather than silently ignored, and the schema is never rewritten to fit a provider's strict mode.

An **Extraction Target** selects the result unit: the whole document (`per_doc`), each page (`per_page`), or each table row (`per_table_row`). The schema always describes one instance; the target only selects the outer shape (object or array) and the execution unit. It is Configuration data, frozen with the Revision or run snapshot, never inferred from content.

A draft Configuration may be run without publishing: the run freezes an **execution snapshot** on the Job (schema, target, engine parameters) instead of creating a Revision. Published runs still pin a Revision (ADR-0007). This keeps the Configuration the single authoring home while letting the playground iterate without polluting revision history.

## Considered Options

- **Keeping the flat Field Schema and extending it with object/array types**: rejected — it would grow a parallel type system whose review/output mappings no longer exist.
- **Rewriting user schemas to a provider's strict mode** (for example, forcing every property into `required`): rejected — silently changes the extraction contract.
- **Recording draft runs as unpublished Revisions**: rejected — pollutes revision history and blurs what publishing means.

## Consequences

- `description` is the only steering text; the prompt serializes the whole schema, so nesting and `enum` values reach the model with no hand-maintained field table.
- Missing/null semantics follow the full schema: a field is omitted when optional and absent, `null` only when the complete field schema accepts it, and a missing required non-null field is a validation failure — never a fabricated placeholder.
- The Extraction Result's `data` is schema-shaped JSON (object or array); there is no field_meta, review state, or output mapping.
- Long-document two-phase extraction is a deferred hypothesis: documents beyond the model context fail explicitly until evaluation shows chunk-and-collect actually improves quality.
- Usage is recorded for diagnostics only; metering and billing belong to the integrating AI middle platform (ADR-0008).
