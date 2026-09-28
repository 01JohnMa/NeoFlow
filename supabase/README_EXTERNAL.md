# External PostgreSQL + Studio

This profile reuses an existing PostgreSQL server and creates a separate `neoflow` database. It does not start a PostgreSQL container.

Required services:

- `auth` for Supabase users and JWTs;
- `rest` for PostgREST table access;
- `migrations` as a one-shot schema runner;
- `meta` and `studio` for database administration;
- NeoFlow `api` and `api-worker` from `docker-compose.prod.yml`.

Storage, Realtime, Edge Functions, imgproxy and analytics are intentionally omitted because the current NeoFlow code stores files under `UPLOAD_FOLDER` and does not call those Supabase APIs.

Create a `.env.local` file (ignored by Git) with `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB=neoflow`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `JWT_SECRET`, `ANON_KEY`, `SERVICE_ROLE_KEY`, `PG_META_CRYPTO_KEY`, `SUPABASE_PUBLIC_URL`, and the NeoFlow provider settings. Keep the values out of Git and logs.

For the current local PostgreSQL container, use `POSTGRES_HOST=host.docker.internal` and `POSTGRES_PORT=15434`. On a Linux server, use the PostgreSQL server's private address or a Docker host-gateway mapping.

Start the Supabase profile and NeoFlow together:

```bash
docker compose --env-file .env.local \
  -f supabase/docker-compose.external.yml \
  -f docker-compose.prod.yml up -d --build
```

Studio is bound to loopback on `STUDIO_PORT` (default `3001`). On a remote server, use an SSH tunnel or put it behind an authenticated HTTPS reverse proxy. The first run must complete `migrations`; do not delete the `neoflow` database or the PostgreSQL server volume during later restarts.
