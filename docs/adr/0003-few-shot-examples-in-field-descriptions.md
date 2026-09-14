# Few-shot examples live in field descriptions

**Status: accepted**

The separate few-shot examples model (document-level input/output pairs stored in a Configuration and injected into the extraction prompt) is removed. Few-shot guidance lives in each field's description, next to the field it steers, and is added only after a real Extraction Result has been reviewed and confirmed correct. Configuration Drafting never fabricates example values.

This follows how LlamaExtract conveys few-shot examples — inside the schema's field descriptions — and removes the failure mode where generated examples were treated as ground truth before any real document had been processed. The alternative, keeping whole-document input/output pairs, carried more end-to-end context but encouraged a second store of document text and produced examples that were never verified. Deferring the "pull a verified snippet from a reviewed result into a field description" convenience to a follow-up ticket keeps this decision small.
