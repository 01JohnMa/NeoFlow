# Tenant and application access are owned by the enterprise AI middle platform

**Status: accepted**

NeoFlow provides capability APIs only; application registration and access control live in the enterprise's AI middle platform. The Tenant scope — which organization a call belongs to — is established upstream and arrives with each request; NeoFlow uses it for data isolation and ownership but does not onboard tenants, issue credentials, or keep its own application registry. This is deliberate: the middle platform already knows the applications and their organizations, and duplicating that registry inside NeoFlow would create two sources of truth for access.

## Considered Options

- **Building NeoFlow's own API-key and application registry**: rejected — duplicates the middle platform and splits the source of truth for access.
- **Managing tenants inside NeoFlow (registration, department selection)**: rejected — belongs to the earlier in-console business model, superseded by the API-first positioning.

## Consequences

- The console keeps authenticating its own administrators; external identity and credential mechanics are an integration concern owned by the middle platform, tracked separately.
- Every resource NeoFlow persists still carries the Tenant key, and every read or write validates that the request's Tenant matches the resource's Tenant.
- If a request cannot present a verified Tenant scope, NeoFlow fails closed rather than falling back to a default tenant.
- The concrete assertion format (signed token versus trusted internal channel) is decided at integration time; the invariant is that only the middle platform's assertion is trusted.
