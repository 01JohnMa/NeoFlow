# NeoFlow Document Processing

NeoFlow turns source documents into structured extraction records via reusable Configurations. The domain model keeps document processing generic while allowing project-specific Configurations and policies to vary behind stable Interfaces.

## Tenancy and projects

**Tenant**:
The ownership and data-isolation boundary for one organization using NeoFlow. It is established upstream by the integrating application and the enterprise AI middle platform that registers applications, and arrives with each request; NeoFlow isolates by it but never onboards, registers, or manages it. A Tenant owns one or more Projects.
_Avoid_: account, customer workspace, department (internal org units are not Tenants)

**Integrating Application**:
An application registered in the enterprise AI middle platform that consumes NeoFlow capabilities on behalf of one Tenant. NeoFlow does not manage its registration or credentials.
_Avoid_: client, API consumer, customer

**Project**:
A workspace within one Tenant that owns Configurations, Processing Jobs, and Extraction Results.
_Avoid_: application, global workspace

## Documents and extraction

**Document**:
A source file tracked through ingestion and extraction. A document may participate in a Composite Extraction with other documents.
_Avoid_: upload, file record

**Document Kind**:
The stable semantic kind of a source document used to select an extraction policy. It is chosen by the operator, not inferred from sample content. It is not a database table name or an external output name.
_Avoid_: raw `document_type` string, result table, AI-predicted type

**Document Ingestion**:
The act of accepting source documents into a Project. Extraction is initiated separately; ingestion no longer implies a Processing Job.
_Avoid_: upload flow

**Extraction**:
The derivation of structured values from one source document under a Configuration's schema and Extraction Target.
_Avoid_: OCR result, LLM response

**Extraction Result**:
The structured values produced for one Document by Extraction, in the shape selected by the Extraction Target: one object or an array of objects. NeoFlow 2.0 does not define business-level sample semantics in this contract.
_Avoid_: raw JSON, business table row, per-page sample

**Parse Result**:
The page- and block-structured markdown produced for one Document by Parsing, and the sole input to Extraction. Stored per Document and reused by every Configuration that consumes that Document.
_Avoid_: OCR text, raw text

**Parse Mode**:
The parsing pipeline a Parse job runs — fast (`pipeline`) or high-precision (`vlm`). It is never inferred from document content; it may be supplied by the caller or defaulted by tenant policy.
_Avoid_: tier, model version, OCR mode

**Extraction Target**:
The result unit of one Extraction run — the whole document (`per_doc`), each page (`per_page`), or each table row (`per_table_row`). It selects the outer shape of the Extraction Result, never the schema of one instance. Chosen in the Configuration, never inferred from content.
_Avoid_: granularity, chunking strategy, field scope

## Configurations and fields

**Configuration**:
A project-owned, reusable definition of one document-processing operation. Its Configuration Type selects the allowed parameters, including the relevant schema and Extraction Target.
_Avoid_: Template, department-specific application

**Configuration Type**:
The operation family defined by a Configuration, such as Extract, Classify, Split, or Composite Extraction. Each type has its own parameter contract while sharing ownership and revision rules. Parse is a parameterized capability rather than a Configuration Type (ADR-0007); historical parse configurations remain readable.
_Avoid_: application type, route type

**Configuration Revision**:
An immutable historical form of a Configuration. A template-based Processing Job runs exactly one Configuration Revision; a parameterized capability records an execution spec instead (ADR-0007).
_Avoid_: mutable configuration snapshot, current template

**Configuration Drafting**:
The interactive flow that proposes a draft extraction schema from a sample Document's Parse Result, for an operator to confirm before the Configuration is created. The Document Kind and Tenant are chosen by the operator up front; drafting never invents example values — few-shot examples live in field descriptions and are edited by the operator (ADR-0003).
_Avoid_: AI wizard, auto template, SDK session

**Processing Job**:
An execution request that applies one immutable execution definition — a Configuration Revision for published runs, or a recorded execution snapshot/spec for parameterized capabilities and draft runs — to a defined set of input Documents.
_Avoid_: background task, batch record

**Field Schema**:
The schema of one instance extracted by an Extract Configuration. In NeoFlow 2.0 it is a JSON Schema subset; each field's `description` is the natural-language guidance that steers the extractor and the home for few-shot examples.
_Avoid_: dynamic database column, ad hoc field mapping

**Field Value**:
A value for one schema field in an Extraction Result.
_Avoid_: untyped dictionary entry

## Composite processing

**Composite Extraction**:
A future, explicitly scoped operation for combining multiple source documents. It is not part of the NeoFlow 2.0 document-processing contract.
_Avoid_: generic merge mode, paired batch, sample alignment

**Logical Sample**:
A deferred business concept. NeoFlow 2.0 does not use it as a Result, review, or routing contract; a future business context must define it separately before implementation.
_Avoid_: per-page sample, implicit sample key

**Provenance**:
The source document, page, or extraction attempt that explains where a Field Value came from. Field-level sources are not part of the NeoFlow 2.0 contract; when they arrive they attach beside the result, never inside its schema-shaped values.
_Avoid_: debug metadata
