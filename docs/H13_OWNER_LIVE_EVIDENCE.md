# H13 owner-operated synthetic live smoke test

Owner evidence supplied in chat during the November 1, 2026 test session
(America/New_York). Runtime pin d2d2906153da5930b70ca45ce1a433dbc797d40e.
Assistant guided execution; the owner operated the Mac and Telegram. This is not
independently observed execution or a general reliability claim.

## Observed evidence

Owner reported Intel macOS 15.7.9, Python 3.14.10; isolated checkout matched the pin,
pip check found no broken requirements, 383 tests passed in 7.71s, and reviewer
OpenAPI check returned without a reported error. Cloudflared reported 2026.10.7.
Private directory permission was 0700; Time Machine exclusion verified. No other
backup service reported; manual external-drive copies were to exclude private state.
A dedicated bot and temporary HTTPS route were used; no production proxy changes.

After approved setup, both loopback/public POST probes without the webhook secret
returned fixed 403 rejected. Owner reported successful webhook registration. Telegram
returned disclosure synthetic-owner-v1; owner chose session-only, supplied invented
values, reviewed revision 1 and confirmed it before the separately approved evaluation.

| Invented input | Value |
| --- | --- |
| Equipment / arrangement | 26-foot box truck / owned |
| Complete payout | $420 |
| Loaded / deadhead / reposition | 180 / 40 / 20 miles |
| Trip duration / schedule assertion | 6 hours / feasible |
| All-operating-mile revenue target | $2.00/mile |
| All-category planning CPM | $1.25/mile |

Owner pasted the live Telegram result: NEGOTIATE, 240 miles, $300 planning cost
including reserves and $120 planning surplus, with no booking/regulatory clearance.
The scoped model selection is required by this runtime to produce that canonical
result; the owner's outcome supports one live integration case, without a separate
provider trace, response export or independently verified billing record.

/refresh recovered the confirmed revision prompt and same step identifier. /forget
produced no Telegram reply on the tested pin. This was confirmed to be the code's
silent privacy path, not interpreted as proof of delivery or deletion. The owner then
removed the webhook successfully, stopped the tunnel, stopped the pilot normally and
reported exit code 0. Closed read-only aggregate database inspection returned:

- Reserved model attempts: 1.
- Saved profiles: 0.
- Pending deletions: 0.
- Privacy commands: completed, count 1.
- Evaluations: completed, count 1.

These records support completed privacy processing and one reserved application
attempt. They are not independently verified provider request counts or proof of
external-history erasure. Session-only consent meant no persistent profile save was
requested. Explicit spending authorization was existing credits only, no out-of-pocket
spending; final provider credit usage and enforcement of account billing cutoff were
not verified. No second evaluation is authorized by this record.

## Follow-up candidate, not live-tested

The next code change adds a best-effort /forget acknowledgement after access is
withdrawn and deletion intent is durable. Copy states active session cleared and
saved-profile deletion requested, not deletion completed or external histories erased.
Acknowledgement uses retained bounded sender capacity outside the inbox lock, bypasses
conversation admission, and never rolls back withdrawal or triggers webhook retries
on sender failure. Duplicate privacy updates do not resend. A dispatch guard suppresses
superseded acknowledgements after fresh consent or a newer privacy request; it cannot
recall a send already authorized. Deletion completion remains the worker's job.

No automatic acknowledgement retry/outbox is claimed. Capacity exhaustion, timeout or
cancellation can still make the acknowledgement absent/uncertain. A future user-facing
privacy-status command could address that gap. The successful live evidence applies
to d2d2906, not to this subsequent acknowledgement implementation.

The test is stopped. No merge, redeployment, new live send, real opportunity,
screenshot extraction or invited-carrier validation is included in this follow-up.
Private config/database retirement remains an owner closeout task under the deployment
plan; this document neither deletes them nor authorizes budget reset. Existing Axle
concept/brand/infrastructure predate the hackathon; this is standalone implementation
evidence, not native Muse connector support or verified economic benefit.

Offline validation of follow-up: 386 tests passed in 8.13s; dependency and reviewer
OpenAPI checks passed. Three added cases verify withdrawal precedes reply, duplicate
suppression, sender failure preserving deletion, and privacy admission despite occupied
conversation slots. The existing stalled-flow test now stalls conversation deliveries
only, allowing the new privacy acknowledgement to use its actual bounded executor.
