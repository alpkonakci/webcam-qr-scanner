# Main readiness audit — 2026-10-03

Historical pre-fix audit. The user-authorized local remediation and its new
results are recorded in [the 2026-10-04 follow-up](main-readiness-fixes-2026-10-04.md).
The original failures below are preserved as evidence, not current local results.

## Decision

**Do not merge or promote to stable yet.** Normal functional checks pass, but
the restart replay gate fails. This is an internal source/test review, not the
independent protocol/cryptography review required for stable v0.2.0.

Baseline: `e21dbe2af46eb80857b857a67b6010b474926bf4`, branch
`codex/vercel-supabase`. This audit adds tests, a failing release-gate probe and
documentation only. Application code, published EXE/ZIP, pairing data, cloud
configuration, release tags and `main` are unchanged. Nothing was merged,
published or pushed during this audit.

## Repeated checks

| Check | Result | Scope / evidence |
| --- | --- | --- |
| Desktop suite | 239 passed | `python -m unittest discover -s tests -q`; includes six new recovery timing/lifecycle tests |
| PWA suite | 47 passed | Production build + Node tests; four new Vercel negative-path tests and one expired-receipt characterization |
| TypeScript / ESLint | Passed | A new test's `prefer-const` lint finding was repaired and targeted tests/typecheck/lint repeated |
| Python / independent Node vectors | Passed | Existing Python vector tests and `node protocol/verify_vectors.mjs` |
| Browser-compatible WebCrypto vectors | Passed | `node protocol/verify_vectors_webcrypto.mjs`; not a physical Safari/Chrome run |
| Packaged beta.2 self-test | Exit 0 | Waited for extracted published-version EXE `--self-test` to finish |
| Retained ZIP SHA-256 | Matches published beta.2 | `E3B0F6388EB2CBB9DFF9C11B590D25C09E7935665D051BBF881B85F08B848115` |
| Gitleaks 8.30.1, all Git refs | No findings | 45 commits, existing exact reviewed fingerprint exclusions; redacted output |
| Gitleaks, generated client bundle | No findings | `pwa/.next/static`, no client exclusions |
| Public production home / health | HTTP 200 | `https://qrwebcam.vercel.app`; health exposes only status/protocol/transport |
| Production public config | Expected fields only | protocol/url/publishableKey/fallback_poll_seconds/connected_resync_seconds; 5s and 60s |
| Anonymous table access | All five HTTP 401 | Public key, GET `select=*&limit=0`; no user rows downloaded |
| Restart replay gate | **FAIL, exit 1** | `python -m protocol.check_receiver_restart_replay` |

The public table-access check covers the anonymous API-key role, not an
authenticated anonymous-device JWT, every RPC privilege or every live policy.
No new Supabase user/device/session was created for this audit.

### Recovery / negative-path coverage added

`tests/test_receiver_recovery_timing.py` exercises the actual `PcReceiver`
control loop with controlled HTTP and Realtime transports. It verifies:

- Healthy connection selects the default 60-second safety resync.
- Disconnected connection selects the default five-second fallback.
- Disconnect interrupts the resync wait and switches to fallback.
- Reconnect switches back to the 60-second interval.
- A real event wait is interrupted by a wake-up; cancellation leaves no waiters.
- Each controlled delivery invokes the callback and posts its ACK exactly once;
  the background Realtime task is cancelled at shutdown.

Intervals are selected using deterministic waits, not measured cloud traffic.
This strengthens automated evidence but **does not close the deployed forced
Realtime interruption / timing gate**.

The new Vercel tests verify that offline/stale receivers produce no delivery
write, malformed metadata is rejected before insertion, receiver credentials
cannot claim another device's messages, and a database uniqueness conflict
returns `replay_rejected` without exposing raw database details. These are
mocked backend tests, not a live Postgres concurrency test.

### User-attested iPhone late-delivery acceptance

The user supplied sequential screenshots of Awaiting receipt and Received by
PC, then confirmed that one PC approval appeared, was approved and opened the
site. This closes that specific iPhone pending/check/receipt/open test. It does
not prove a receipt checked after its expiry, deduplication across reloads/tabs,
an Android test, or which transport delivered the message. Phone/browser
versions and exact network/receipt timing were not recorded.

## Findings requiring follow-up

### R1 — High: receiver reconstruction forgets accepted message IDs

`bridge/replay.py` retains message-ID digests only in memory. Each
`PcReceiver` constructed by `ReceiverService` gets a new guard. The isolated
release probe authenticates one envelope, confirms same-instance replay is
rejected, then reconstructs the production receiver and observes the same
still-valid envelope accepted again. No URL is opened and no real credentials
or network are used.

This is reproducible evidence that the promised persistent PC replay gate is
not implemented. It is not evidence of an attack in production. A normal
delivered row can prevent ordinary re-delivery while present, but a client
must not rely solely on an untrusted relay to enforce replay protection.

Required remediation: a bounded, pair-scoped, current-user protected replay
ledger retained across receiver recreation and process restart, with atomic
updates, corruption/failure handling and expiry tests. Do not store URL history.
Also avoid `replay_guard or InMemoryReplayGuard()` replacing an explicitly
provided empty guard because that guard defines `__len__`.

### R2 — High, source-review finding: database replay retention ends too early

In `pwa/server/relay-handler.ts`, `acknowledgeDelivery` shrinks the delivery
row's expiry to the ACK expiry (normally receipt time + 10 seconds). The
Supabase `relay_cleanup` function deletes that row after expiry. The only
database uniqueness tombstone is `unique (pair_id, message_id)` on that row,
while the original encrypted URL may still be valid for up to 300 seconds.

Source therefore permits losing the database replay tombstone before the URL
replay window ends. With R1 and receiver reconstruction, defense layers are
insufficient for the stated gate. No live replay against production was
attempted; this conclusion is from the handler and committed SQL migration.

Required remediation: separate short receipt/envelope retention from replay
tombstone retention. Preserve bounded opaque ID/digest uniqueness for the full
authenticated message lifetime without unnecessarily retaining ciphertext.
Test cleanup + replay + reconnect/restart together before deployment.

### U1 — Medium: delayed manual receipt checks can miss the valid ACK

ACK lifetime is ten seconds, but after the initial 15-second wait the phone
only checks again on a manual button press. A receipt first checked after its
expiry cannot be verified; the real relay may instead return expiry or remove
the receipt. The new characterization test confirms that an expired encrypted
ACK cannot falsely produce Received by PC and does not cause another POST.

The successful user test does not eliminate this timing limitation. Suggested
remediation: bounded receipt watching while the page remains open, caching
only an authenticated success; handle expired/unknown status honestly. Do not
silently weaken cryptographic expiry or claim that a status-only response is
an authenticated receipt. Background/suspended mobile pages need explicit
limitations. Page reload and separate tabs also remain outside the current
memory-only duplicate-attempt guard.

## Security requirement mismatches / review notes

- The Vercel implementation hashes bearer tokens with plain SHA-256, not the
  peppered HMAC stated in the design/checklist. Tokens are high-entropy random
  values; this mismatch alone is not proof of practical token recovery. The
  rate-limit fingerprint uses SHA-256(pepper + separator + address), not HMAC.
  Reconcile the design or implementation through security review.
- Pairing/results/ACKs and pending encrypted envelopes are stored in Postgres,
  not memory-only as the original threat-model checklist says. Offline sends
  with a stale heartbeat are rejected, but sends accepted within the online
  grace can arrive later. Document actual retention semantics and account for
  probabilistic cleanup (not a guarantee of immediate physical erasure).
- Production CSP blocks other script origins and framing, but script-src
  includes `unsafe-inline`; it is not a nonce/hash-only strict script policy.
  No XSS was demonstrated by this review. Keep the strict-CSP gate open.
- Current DPAPI use is user-scoped; root CryptoKey creation/storage is
  non-extractable HKDF; URL/ACK/pairing keys use distinct KDF contexts; AEAD
  binds metadata; URL confirmation defaults to No; receipt precedes the user's
  decision and does not reveal the decision. Source and existing tests support
  these items, not an independent cryptographic certification.

## Checks not finishable from current evidence

- Actual Android Chrome extended reboot, different-network, offline/recovery,
  and revocation matrix (the earlier Android core flow remains user-confirmed).
- Forced Realtime interruption and observed healthy/fallback request timing
  against an isolated deployed device. Do not intercept the user's real pair
  or pretend deterministic unit transport mocks are a live test.
- Broader production log/error-path review, Auth logging, live authenticated
  policies/RPC privileges and data-retention verification. The previous log
  sample is retained evidence, not a fresh blanket certification.
- Independent protocol/cryptography review by a separate qualified reviewer.

## Next order

1. Remediate R1/R2 together and add restart/cleanup/concurrency regressions.
2. Resolve U1 and retest the late-check path, not only immediate Check status.
3. Reconcile security/privacy requirements with the implemented relay.
4. Complete isolated deployed transport tests, real Android acceptance and
   independent security review; then reassess PR #3 for main.

No main merge or stable-release recommendation follows from green unit tests
while the separate release gate fails.
