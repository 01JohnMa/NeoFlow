# NeoFlow Document Processing

NeoFlow turns one or more source documents into reviewable, structured records and optional external outputs. The domain model keeps document processing generic while allowing project-specific Configurations and policies to vary behind stable Interfaces.

## Tenancy and projects

**Tenant**:
The ownership and data-isolation boundary for one organization using NeoFlow. A Tenant owns one or more Projects.
_Avoid_: account, customer workspace, department (use Tenant even when the UI groups by department, e.g. 质量管理中心)

**Project**:
A workspace within one Tenant that owns Configurations, Processing Jobs, and Extraction Results.
_Avoid_: application, global workspace

## Documents and extraction

**Document**:
A source file tracked through ingestion, extraction, review, and completion. A document may participate in a Composite Extraction with other documents.
_Avoid_: upload, file record

**Document Kind**:
The stable semantic kind of a source document used to select an extraction policy. It is chosen by the operator, not inferred from sample content. It is not a database table name or an external output name.
_Avoid_: raw `document_type` string, result table, AI-predicted type

**Document Ingestion**:
The act of accepting source documents, associating them with a Project and Configuration, and creating a Processing Job.
_Avoid_: upload flow

**Extraction**:
The derivation of field values from one source document under a Configuration's Field Schema and extraction policy.
_Avoid_: OCR result, LLM response

**Extraction Result**:
The structured, provenance-aware values produced for one Document execution by Extraction. NeoFlow 2.0 does not define business-level sample semantics in this contract.
_Avoid_: raw JSON, business table row, per-page sample

**Parse Result**:
The page- and block-structured markdown produced for one Document by Parsing, and the sole input to Extraction. Stored per Document and reused by every Configuration that consumes that Document.
_Avoid_: OCR text, raw text

**Parse Mode**:
The parsing pipeline a Parse job runs — fast (`pipeline`) or high-precision (`vlm`) — chosen by the operator, never inferred.
_Avoid_: tier, model version, OCR mode

## Configurations and fields

**Configuration**:
A project-owned, reusable definition of one document-processing operation. Its Configuration Type selects the allowed parameters, including the relevant Field Schema and processing policies.
_Avoid_: Template, department-specific application

**Configuration Type**:
The operation family defined by a Configuration, such as Parse, Extract, Classify, Split, or Composite Extraction. Each type has its own parameter contract while sharing ownership and revision rules.
_Avoid_: application type, route type

**Configuration Revision**:
An immutable historical form of a Configuration. Every Processing Job runs exactly one Configuration Revision.
_Avoid_: mutable configuration snapshot, current template

**Configuration Drafting**:
The interactive flow that proposes a draft Field Schema (and later an extraction prompt) from a sample Document's Parse Result, for an operator to confirm before the Configuration is created. The Document Kind and Tenant are chosen by the operator up front; drafting never invents example values — examples reach field descriptions only after real results are verified.
_Avoid_: AI wizard, auto template, SDK session

**Processing Job**:
An execution request that applies one Configuration Revision to a defined set of input Documents.
_Avoid_: background task, batch record

**Field Schema**:
The set of fields recognized by an Extract or Composite Extraction Configuration, including each field's key, label, type, description (natural-language guidance that steers the extractor, and the only home for few-shot examples), requiredness, validation rules, provenance, and output mapping.
_Avoid_: dynamic database column, ad hoc field mapping

**Field Value**:
A value for one Field Schema entry, together with its source/provenance and validation state when available.
_Avoid_: untyped dictionary entry

## Composite processing

**Composite Extraction**:
A future, explicitly scoped operation for combining multiple source documents. It is not part of the NeoFlow 2.0 document-processing contract.
_Avoid_: generic merge mode, paired batch, sample alignment

**Logical Sample**:
A deferred business concept. NeoFlow 2.0 does not use it as a Result, review, or routing contract; a future business context must define it separately before implementation.
_Avoid_: per-page sample, implicit sample key

**Provenance**:
The source document, page, or extraction attempt that explains where a Field Value came from.
_Avoid_: debug metadata

## Review and outputs

**Review**:
The human validation step that can correct Field Values and approve or reject an Extraction Result before an output is emitted.
_Avoid_: manual patch, status toggle

**Output Policy**:
The Configuration-owned rules that decide which approved values and source artifacts are emitted, including naming and attachment behavior.
_Avoid_: push logic

**Output Adapter**:
An Adapter that translates an approved Extraction Result into an external sink such as Feishu or a fixed Excel document.
_Avoid_: provider-specific route

**Business Adapter**:
An Adapter that supplies tenant- or business-specific Configuration parameters without changing the generic processing flow.
_Avoid_: copied business route, special-case branch
