# Legacy complete-Parse page routing (superseded)

**Status: superseded by [ADR-0011](0011-source-page-routed-index.md)**

This ADR is retained only as a record of the retired `page_routed` experiment. It is not an executable Configuration strategy and must not be accepted by new revisions or Job snapshots. The experiment indexed pages from a complete ParseResult and changed only the LLM context; it did not provide on-demand source parsing.

The supported strategies are now:

- `full_document`: parse the source inside the current Extract Job and extract from that Job-owned complete ParseResult.
- `source_page_routed`: index the uploaded source first, Parse only selected physical pages inside the current Extract Job, and extract from that Job-owned partial ParseResult.

Both strategies keep ParseResult ownership, retries, and database binding at the Extract Job boundary. See ADR-0011 for the current source-first contract. Historical benchmark files may mention `page_routed`, but the runtime rejects that value.
