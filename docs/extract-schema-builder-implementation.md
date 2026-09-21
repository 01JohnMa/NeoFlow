# Extract Schema Builder implementation

## Decisions

`data_schema` is the only extraction contract. The Builder edits it directly;
JSON is an alternate editor of the same draft. Only one editor is active at once.
There is no stored recursive fields DSL and no runtime fields compiler.

**No historical compatibility:** no fields fallback, data migration, schema
conversion, or rewriting old Revisions. Fields-only configurations must be
recreated. A new empty draft explicitly receives an empty object schema; invalid
or missing schemas in saved definitions are not substituted with defaults.

Extract definitions contain only `target`, `data_schema`, and optional `ui`.
The full existing execution schema subset remains unchanged. Builder capability
is narrower than that subset, not a new execution constraint. Valid schemas
outside the Builder profile remain editable as raw JSON without conversion.

UI metadata is `{schemaJsonPointer: {label?, order?}}`; labels and order cannot
change extraction semantics. Hints edit `description` on the corresponding
schema node. Changing schema/UI replaces each complete section atomically.
Unknown Extract settings and stale UI pointers are rejected instead of being
saved but ignored.

## UI scope

Builder supports text, date, number, boolean, string enum and object lists.
Object-list elements contain scalar fields, not additional lists or objects.
Child required stays on the item object, never propagates to the list or root.
Rename synchronizes local required and descendant UI paths. Duplicate keys are
rejected before object-map construction. Raw JSON also rejects duplicate keys.

Field edits apply to the in-memory draft, then Save persists that same schema.
Publish is disabled until unsaved edits are saved or explicitly discarded.
Archived configurations are read-only. JSON preview is not represented as the
saved execution definition while the draft has unsaved changes.

## AI drafting boundary

The existing three-type proposal form is retained for this iteration. Its
transient confirmed rows materialize into schema once at authoring time;
proposals are not persisted as executable fields. Name/code remain user-owned.
Generated overall guidance is saved in root `schema.description`, not a dead
`extraction_prompt` key. It no longer requires a document placeholder or filling
missing values with empty strings. The commit action creates a draft, not a
published Revision. Enum/object-list authoring is completed in Builder.

## Result display

The API adds an independent read-only `view` beside raw `data` and `engine`.
It uses the result Job's frozen execution_spec, or its exact pinned Revision.
It never fetches the current configuration. Revision UI metadata is pinned;
draft Jobs without frozen UI metadata show keys. No changes are made to Job
snapshot format to add presentation metadata.

Schema hash mismatch, missing binding or metadata failure makes the view
unavailable while raw result retrieval remains available. Descriptions are
omitted from the display projection; the hash still identifies the original
execution schema. Authorized result data and JSON exports are never rewritten.

The UI distinguishes completed results, queued/processing, failed, load failure,
and missing formal result. A missing property means “未返回”, not “原文没有”.
Presence checks preserve `false`, `0`, `null`, empty strings, arrays and objects.
Only actual product rows are rendered. `per_page` outer instances remain
separate from product arrays inside an instance. Coverage is not accuracy.

## Seed

`configurations/seeds/prj-basic-info-drug-registration.json` describes 38 top-level
fields, 8 top-level string enums, and two object lists with 5 child fields each.
Only the two item-level `name` fields are required. The root remains sparse.
Date guidance rejects invented days for month-only evidence. Scenario labels
are not injected as extracted default values. Training response envelopes and
confidence/source fields do not become formal extraction data.

`python scripts/seed_extract_configuration.py --base-url <API> --tenant-id <TENANT>
--project-id <PROJECT>` requires `NEOFLOW_API_TOKEN` in the environment. The script
uses the normal admin API, never SQL. It creates a draft, skips an identical
record, and rejects a conflicting record. It neither publishes nor overwrites.
Run it explicitly after deployment; no seed is executed by installing the code.

## Unchanged execution boundaries

Claim/commit, Parse Result binding, execution unit planning, Job snapshots,
per_doc/per_page outer shapes, request budgets and the one-repair validation loop
are unchanged. Only the retired schema-source fallback is removed. Result storage
remains read-only through these display APIs.

## Verification

Run Python configuration/view/seed tests and the existing execution/route/SDK
suite. Run frontend Vitest and `npm run build`. Browser acceptance must include
field rename, item-required editing, a schema enum change affecting a new run,
unsaved publishing protection, archived read-only state, false/zero rendering,
and a past result after current configuration edits.
