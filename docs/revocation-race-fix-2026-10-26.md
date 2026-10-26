# Delivery / revocation race fix

## Invariant and scope

An HTTP send authorized before removal must not enqueue after revocation wins
the pair-row lock. The BEFORE INSERT trigger locks that row and checks current
revocation and device ownership. The existing removal UPDATE takes the same
lock: enqueue-first is subsequently deleted; revoke-first is rejected. The
claim RPC also excludes pairs whose revocation is visible to its statement.

This does not retract a response already claimed/sent before revocation or
cancel a confirmation already displayed. Desktop key removal remains required.
No plaintext, token, or existing pairing data is added or exported.

## Verification

- RED: baseline SQL accepted the post-revocation insert; HTTP test returned 503
  instead of the dedicated 410 response.
- GREEN: embedded PostgreSQL (PGlite) tests cover both serial orderings, active
  and expired leases, revoked claims, mismatched device IDs, service-role
  operation and denied browser-role access.
- 148 web tests and 348 desktop tests passed; ESLint and TypeScript passed.
- Default `npm test` stopped at a local Turbopack child-process panic. Explicit
  Webpack production build and postbuild runtime-boundary check passed; web
  tests were then run separately. Do not label default Turbopack build passed.
- CI now runs the SQL checks in a separate disposable PostgreSQL database,
  including two-session lock-contention checks in both directions.
- Follow-up: both real multi-session checks passed locally on portable
  PostgreSQL 17.11, using a new disposable cluster and the fixed loopback
  database `wqrs_revocation_test`. Active/expired leases, revoked claims,
  device binding and service/browser-role boundaries also passed. The archive
  SHA256 matched its official EDB sidecar:
  `80379b2c04d51c30225532e0ae04509899141e9957ed096fe749d7fd9df8f82f`.
  No Windows service was installed; the temporary server stopped cleanly.
  Output: `build/postgres-revocation-test-20261026/result.txt`.
  This was a local PostgreSQL run, not a claim that remote CI already ran.
- Scoped independent AI review found no correctness blocker in the trigger
  design; it is not a human security audit.

## Rollout (not performed)

1. The local PostgreSQL checks passed; run the same checks in remote CI before
   rollout after committing/pushing the reviewed change.
2. Deploy the handler mapping SQLSTATE P0410 to HTTP 410 / pair_revoked first.
3. Apply `supabase/migrations/202610260001_serialize_delivery_revocation.sql`.
   It changes functions and a trigger transactionally; it deletes no records.
4. Verify ordinary send, removal, revoked send and re-pair using test devices.

No desktop EXE rebuild is required for this server/database-only fix. Neither
production Supabase nor Vercel nor main was changed in this work. If the new
migration is not installed, the old race remains live regardless of the HTTP
error mapping. An older handler remains fail-closed with the new trigger but
may show a generic 503 instead of the dedicated revoked message.

Rollback requires restoring the previous claim function and dropping only the
new trigger/function; that reopens the original race. Do not roll back casually.
