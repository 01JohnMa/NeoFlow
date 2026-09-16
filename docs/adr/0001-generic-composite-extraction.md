# Keep business adaptation behind the composite extraction interface

**Status: superseded by ADR-0004**

The earlier proposal to make multi-document and multi-page processing a first-class Composite Extraction capability is deferred. NeoFlow 2.0 remains document-centric; it does not define sample alignment, merge cardinality, or sample review semantics in the core platform.

Any future business composition must be specified separately and enter through an explicitly scoped Adapter or a new ADR. It must not add business-specific merge branches to generic routes, workers, or Result contracts.
