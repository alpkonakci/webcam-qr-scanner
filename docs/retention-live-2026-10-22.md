# Live retention activation — 22 October 2026

User explicitly requested activation and live verification. Target verified in
the authenticated dashboard: `webcam-qr-scanner`, project
`uburlufyreciuoabaone`, database/role `postgres`.

Preflight: existing `public.relay_cleanup(bigint)` matched the reviewed cleanup
logic (empty search_path, expired one-time pairings/deliveries/rate keys and ACK
content). Neither anon nor authenticated could execute it. Saved phone pairings:
28. The dashboard reported Healthy. pg_cron was available at version 1.6.4 but
not installed. The dashboard reported no backups; activation did not change
backup configuration or rerun historical data migrations.

Applied the guarded extension prerequisite and the reviewed
`supabase/operations/install_retention_cron.sql` operation through SQL Editor.
No existing Cron jobs were present after extension installation. Created job 1,
`wqrs-relay-retention-v1`, active, schedule `*/5 * * * *`, with the reviewed
30-second statement / 2-second lock timeout command. No manual cleanup execution
was used to substitute for scheduler verification.

The first **automatic** run succeeded:

- Started: `2026-10-21T21:45:00.104721Z`.
- Finished: `2026-10-21T21:45:00.113280Z` (22 October, 00:45 Europe/Istanbul).
- Saved pairings before/after: **28 / 28**.
- Expired one-time pairing requests: **1 → 0**.
- Expired deliveries: **1 → 0**.
- Expired rate keys: **2 → 0**.

Counts and run metadata were read back at 21:45:22 UTC. No phone keys, URLs,
payloads or credentials were selected. One interim status query failed because
the browser editor replaced only the visible input portion; it was corrected
by selecting and clearing the full editor. The failed query made no data changes.

Screenshot evidence: `build/retention-live-20261022/live-cron.png` (local ignored
artifact). For ongoing checks use `check_retention_cron.sql`. To stop only this
schedule use `uninstall_retention_cron.sql`; deleted expired records cannot be
restored by unscheduling, and request-driven cleanup remains active.

This verifies installation and the first hosted scheduler execution. It does
not prove long-term availability, alter the released EXE, or merge PR #3.
