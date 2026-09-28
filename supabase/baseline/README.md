# NeoFlow fresh-install baseline

`000_final_public_schema.sql` and `001_wetrial_configuration.sql` are generated
from the verified PostgreSQL 16 external profile. They are for an empty
database only:

```text
MIGRATION_MODE=baseline MIGRATIONS_DIR=/baseline
```

The baseline includes the final `public` schema, NeoFlow's `auth.uid` /
`auth.role` / `auth.jwt` compatibility helpers, the profile trigger, the
`wetrial` tenant, and the published drug-registration Configuration/Revision.
It excludes GoTrue's `auth` tables, users, documents, jobs, results,
embeddings, and provider credentials. GoTrue must be started before running
the baseline so its Auth schema exists.

Existing databases must keep using `supabase/migrations`; the runner rejects
baseline mode when `schema_migrations` is non-empty. Historical migrations are
kept for upgrade and auditability rather than deleted from the repository.
