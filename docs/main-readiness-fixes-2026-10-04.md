# Main readiness fixes — 2026-10-04

Historical local-fix snapshot. The subsequent migration/package/publication
status is recorded in [beta.3 verification](v0.2.0-beta.3-verification-2026-10-04.md).
The deployment limitations below describe this snapshot, not a later rollout.

User-authorized remediation of R1/R2/U1 from the
[2026-10-03 audit](main-readiness-audit-2026-10-03.md). Work started on October 3
and verification finished after midnight in Europe/Istanbul. These are local,
uncommitted changes on `codex/vercel-supabase`, baseline `e21dbe2`.

## Decision and scope

The three findings have source fixes and passing local regressions. **This is
not a main/stable release approval or a deployed fix.** No push, merge, cloud
migration/deployment, tag movement or published artifact replacement occurred.
Existing pairing credentials were not read, changed or removed by the tests.

## Changes

- R1: `ReceiverService` gives every pair a relay-origin/pair-scoped
  `PersistentReplayGuard`. Reconnects and new processes use the same
  `message-replay.sqlite3` next to the DPAPI pairing store. Its entire record
  payload is current-user DPAPI ciphertext: scoped message-ID digests and
  expiry only, never URLs, tokens or keys. SQLite transactions serialize
  writers; capacity/format/expiry checks are bounded. Corrupt or unavailable
  storage fails closed without an ACK or URL callback. An explicit empty
  in-memory guard is no longer replaced through truthiness.
- R2: Supabase and legacy D1 handlers retain `(pair_id, message_id)` uniqueness
  until the original URL expiry, not the ten-second receipt expiry. Terminal
  deliveries clear URL ciphertext. Cleanup clears expired ACK ciphertext
  separately. Expired or removed receipts return `delivery_receipt_expired`,
  not a forged authenticated success. Supabase migration:
  `supabase/migrations/202610030001_separate_receipts_from_replay.sql`.
- U1: after the initial receipt wait, the phone watches the existing delivery
  using GET only every 1.5 seconds while the result remains open. Receipt
  requests time out after eight seconds; unmount/leave aborts them. Valid
  cryptographic success is cached in page memory. A receipt whose verification
  window was missed shows **Check your PC**, blocks a duplicate send for that
  attempt, and does not claim **Received by PC**. ACK cryptographic lifetime
  remains ten seconds.

## Verification

| Check | Local result / scope |
| --- | --- |
| Desktop suite | 254 passed; no failures |
| New persistent replay regressions | 15 passed; scoped IDs, bounds, corruption, concurrency, expiry, service reconnect wiring, no ACK/callback on storage failure |
| Windows DPAPI separate-process regression | Passed with temporary synthetic data; not a physical Windows reboot |
| Dedicated receiver restart gate | Passed, exit 0; reconstructed receiver rejects the same authenticated envelope |
| PWA suite | 54 passed; includes GET-only watching, timeout, cancellation, expired receipt and no duplicate POST |
| Next production build / TypeScript / ESLint | Passed |
| Supabase handler retention | Mocked admin tests passed; not live Postgres cleanup/concurrency evidence |
| Legacy D1 retention | Actual Miniflare SQL cleanup + uniqueness test passed through receipt expiry and URL expiry |
| Independent Node / browser-compatible WebCrypto vectors | Both passed; not an independent security review or a physical phone-browser run |
| Candidate EXE | PyInstaller build passed; waited `--self-test`, exit 0 |
| Candidate archive | Contains `bridge.replay`, `bridge.receiver_service`, `sqlite3`, `_sqlite3.pyd`, `sqlite3.dll`, application icon |
| Generated browser assets | Gitleaks 8.30.1: no findings, ~743 KB; redacted scan, no client exclusions |
| Local tracked diff + untracked source/docs | Gitleaks stdin: no findings, ~84 KB; redacted output, no broad new exclusions |
| Render-only browser preview | Accessibility tree confirms disabled Check your PC and honest expired-receipt text; screenshot capture unavailable, so visual/device QA is not claimed |

The local EXE is deliberately separate:
`dist/readiness-fix-20261003/QR-Scanner.exe`.
SHA-256: `F3C8198738522288C04038773106859AEC268F6D0CA72D84DE5D876808E38023`.
Its version metadata still says beta.2: it is an **unpublished local preview**,
not a replacement for the public beta.2 asset. A future release needs a new
version/tag. The retained published beta.2 EXE checksum remains unchanged.

## Limitations and deployment order

1. Validate/apply the new SQL migration in an isolated Supabase/Postgres
   environment first. Neither `psql`, Docker nor Supabase CLI is available
   locally; this migration was source-reviewed but **not executed on Postgres**.
   It repairs surviving legacy terminal rows from their envelope metadata;
   it cannot reconstruct rows already deleted by old cleanup.
2. Deploy the migration and new relay/PWA handler together, then distribute a
   newly versioned EXE. Both relay and desktop defenses matter. Keeping the old
   published EXE/site does not acquire these fixes automatically.
3. Exercise one fresh test pair: normal send, delayed receipt, reconnect and
   receiver restart, remove/re-pair, and uncertain delivery. Record iPhone and
   Android device/browser versions. Force deployed Realtime interruption and
   measure five-second fallback/60-second healthy resync separately.
4. Complete the open privacy/policy/log/RPC/CSP and independent protocol review
   gates before deciding whether PR #3 can merge or become stable.

The ledger is not anti-rollback protection against a malicious actor with the
same Windows account. Expired local digests are pruned on a subsequent valid
message; server cleanup is probabilistic, not immediate physical erasure.
Replay storage is an at-most-once defense, not guaranteed delivery across a
crash between persistence, ACK transmission and presenting the URL.
Safari/background suspension can still miss the short ACK window. Page reload
or another tab does not preserve the page-memory attempt/result registry.
These limitations must not be represented as authenticated delivery success.
