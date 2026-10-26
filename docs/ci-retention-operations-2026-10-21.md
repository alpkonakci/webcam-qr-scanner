# CI and retention operations — 21 October 2026

Status updated 22 October: pushed to the working branch; push and PR CI passed
on `9c48e07fc064f793101e601752a188ba158af802`. Live Cron was activated and its first
automatic execution succeeded. See [activation evidence](retention-live-2026-10-22.md).
Branch protection and a merge to main have not been performed by this work.

## Continuous integration

`.github/workflows/ci.yml` runs on push, pull request and manual dispatch:

- **Desktop (Windows):** Python 3.12.10, isolated `.venv`, dependency consistency
  and the full desktop unit suite.
- **Web (build, tests, lint, types):** Node 22, locked npm install, production
  build, web tests, lint and typecheck.
- **Retention SQL (disposable PostgreSQL):** PostgreSQL 17 with a pinned image
  digest and a synthetic Cron API fixture; no production database connection.

Actions are pinned to full commit IDs. The GitHub token has only `contents: read`,
checkout does not retain credentials, jobs have time limits, and there are no
deployment steps or application secrets. The public database password is only
for the disposable CI service. The SQL job requires `psql` on the hosted runner
and checks its availability before testing.

`requirements-ci-constraints.txt` pins the test CA package to the version whose
corresponding source is bundled in the distribution. Update that constraint and
the bundled source together after dependency review. It does not change runtime
requirements. These tests do not replace real-device or screen-reader acceptance.

After an authorized push, verify all three hosted checks pass before configuring
them as required checks. Local success does not prove the hosted workflow passed.

## Before live retention activation

1. Confirm the intended Supabase project and database, backup/recovery policy and
   explicit activation approval. Deleted expired data cannot be restored merely
   by removing the schedule.
2. Verify all relay migrations are already applied, including
   `202610030001_separate_receipts_from_replay.sql`. Do not blindly rerun migrations
   containing data changes to satisfy this prerequisite.
3. Enable `pg_cron` explicitly if necessary using the versioned
   `supabase/operations/enable_retention_cron_extension.sql` prerequisite or the
   [Supabase Cron installation guide](https://supabase.com/docs/guides/cron/install).
4. Inventory existing cleanup jobs, including unnamed jobs and jobs owned by
   other roles, in the administrator dashboard. SQL job visibility can depend on
   role; the install guard is not a complete cross-owner inventory.
5. As `postgres`, review and execute
   `supabase/operations/install_retention_cron.sql` in that verified project.

This operation registers `wqrs-relay-retention-v1` every five minutes. Installation
does not run cleanup immediately. Reinstallation keeps one matching job and
reactivates it if inactive. A conflicting definition or another visible cleanup
job causes refusal. Public client roles must not have permission to call cleanup.

Each execution uses the existing `public.relay_cleanup(bigint)` function with a
30-second statement timeout and a two-second lock timeout. Saved phone pairings
and devices are preserved. Expired one-time pairings, delivery records and rate
keys are removed; expired acknowledgement content is cleared while the live
replay-prevention record remains. Expiry enforcement and physical deletion are
different: five-minute scheduling is not a deletion guarantee during outages or
timeouts. Large backlogs may require a separately reviewed maintenance plan.

## Check the first run and ongoing health

Execute `supabase/operations/check_retention_cron.sql` after installation and
again after the first scheduled interval (allow approximately six minutes).
It exposes job/run metadata, not link contents or raw error messages.

| Health | Meaning / action |
| --- | --- |
| `not_yet_run` | Newly installed; verify after the first interval. |
| `ok` | A recent successful run exists and the latest run is not failed. |
| `missing`, `inactive` | Schedule absent or disabled; investigate intent. |
| `unexpected_definition` | Stop and inspect configuration before modifying it. |
| `awaiting_success` | No successful execution yet; inspect run history. |
| `failed`, `stale` | Investigate errors or absence of success for 15 minutes. |

The check requires Cron to be enabled. Review run-history retention separately:
Cron history is not automatically purged. Do not delete other jobs' history as
part of this operation. See the official
[Cron quickstart and monitoring guide](https://supabase.com/docs/guides/cron/quickstart).

## Stop the schedule

Review and run `supabase/operations/uninstall_retention_cron.sql` as `postgres`.
It removes only the matching named job, refuses a changed definition and is safe
to repeat. It does not drop the extension or delete unrelated jobs. A running
execution may finish, and deleted rows are not restored. Existing request-driven
server cleanup continues; unscheduling does not disable all retention enforcement.

## Test boundary

`node scripts/check_retention_schedule.mjs --postgres` targets only loopback port
5432 and database `wqrs_retention_test`. Use only a disposable test database.
It refuses existing relay tables/Cron schema. It never reads a production URL or
application environment file. The fixture supplies a synthetic Cron API; it
tests SQL installation, exact registered command, expiry/replay behavior, status
and scoped removal, not the real scheduler or worker.

Local verification can use `--pglite <absolute path to PGlite dist/index.js>` with
PGlite 0.5.10 in an in-memory database. That tool is kept in ignored `build`, not
application dependencies. Actual hosted Cron execution remains a separate gate.

The existing desktop candidate is unchanged. A future combined release must
refresh its source bundle to include the final server/CI changes before publishing.
