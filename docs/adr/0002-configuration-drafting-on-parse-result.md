# Draft configurations from a Parse Result, not from OCR

**Status: accepted**

Configuration Drafting now starts from a sample Document that is parsed by MinerU (parse mode chosen by the operator at upload), and the drafting agent proposes only the Field Schema from that Parse Result. The Document Kind and Tenant are chosen by the operator up front and are never inferred, and drafting has no side channel of its own: no OCR pipeline, no synchronous upload-time extraction. This replaces the previous flow where session creation ran OCR synchronously and the analyzer guessed the document type, department, and example values.

The alternative — keeping OCR for drafting and recommending Kind/Tenant from content — was rejected because MinerU is already the platform's only Parsing path (ADR-adjacent decision #15/#21) and because an inferred identity is an unreliable default for an operator who knows the answer. Parsing is slow (tens of seconds), so a drafting session is identified by its parse Job and can be reopened after a refresh or an API restart by rebuilding from the persisted Job, Document, and Parse Result; no separate session store is introduced.
