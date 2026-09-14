# Keep business adaptation behind the composite extraction interface

**Status: proposed**

NeoFlow will model multi-document and multi-page processing as a generic Composite Extraction capability. Configurations provide the Field Schema, Merge Strategy, review rules, and Output Policy; business-specific behavior enters through Configuration parameters or an Adapter, while routes and workers remain orchestration only. This replaces duplicated business branches for paired documents and field merging with one testable Interface and preserves a seam for future output targets.

The existing electrical, lighting, and other business cases remain compatibility Adapters during migration. New business behavior should not add another route-level merge implementation. Physical result-table mappings and external output details are implementation concerns behind the Repository and Output Adapter Interfaces, not domain terms exposed to callers.
