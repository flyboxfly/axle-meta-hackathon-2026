# Telegram owner increment — November 8, 2026

## Repository inspection

Default branch `main` is ef8b1e5 (H13). The H15 branch is at 1883bc5,
newer than the historical a8508749 baseline. This increment builds on that
H15 branch, retaining its existing callers. H15 also contains legacy Mini App
routes and a factory that mounts them; those are not required by the chat
increment and are not removed here. A chat-only host composition remains work
before deployment under the revised product direction.

Existing chat path: consent, session profile, profile review, PNG/JPEG screenshot,
trip input, exact-revision confirmation, pricing/evaluation, correction and
negotiation guidance in the same chat. Economics uses Decimal. Authorization
maps approved numeric user and private-chat IDs to a carrier separately from
webhook host/secret authentication. The opening profile has no DOT/MC/unit model.

SQLite stores update claims, ordering, paid-attempt budgets and delivery states.
Interrupted processing/sending is marked uncertain on restart and is not blindly
retried. OpeningSessions profiles, opportunity revisions and conversation state
are volatile. The older PilotMemory profile persistence does not establish
persistence of the H15 opening profile. Location pins, truck routing, home/next
stop confirmation, pass records, callback buttons and multiple open loads remain
outside this increment. Existing numeric miles and feasible availability are
carrier assertions, not routing or schedule verification.

## Change

After screenshot intake, ask for a total payout goal. The carrier can send
`I want $480 total` or `payout goal 480`, including the latter with other labeled
trip fields. Total dollars remain canonical, distinct from the broker offer and
minimum job charge. Review shows the equivalent all-mile rate when all mileage
segments are known. Changing mileage recalculates that rate without changing the
payout goal. Switching to `target 2` restores a per-mile target. Two simultaneous
goal bases are rejected. Total goals must be positive, bounded and in cents.

Every correction uses the existing new-revision/confirmation invalidation path.
A new screenshot clears the prior load's total-dollar goal; the carrier must
supply a fresh goal or rate. Unknown repositioning remains unknown. Profit and
daily/weekly language receives clarification without changing the snapshot;
profit-goal calculations and period allocation remain future work. Natural
language support is deliberately bounded; arbitrary paraphrases are not claimed.

The opening-bid calculator continues its existing target/minimum/cost rule.
The revenue gap is not used as an opening bid. Draft negotiation output remains
internal and is never sent to a broker.

## Verification and live boundary

Offline, injected-model/transport tests only. Final verification:
`/tmp/axle-owner-venv/bin/python -m pytest -q` — 648 passed;
focused new module — 15 passed; `git diff --check` — passed. New tests cover the 240-mile,
$420-offer, $1.25-CPM case: $300 cost, $120 surplus, $480 target, $60 gap,
NEGOTIATE; corrections, cents precision, unknown mileage, conflicting goals,
clarification, a no-offer opening bid, new screenshots and webhook replay.

No MODEL_API_KEY, AXLE_PILOT_CONFIG_FILE or TELEGRAM_BOT_TOKEN is configured
in this workspace (presence checked without printing values). H15's provider
configuration selects muse-wonder-1.0 at the Meta Responses endpoint. Credential
validity, current model access, prices and remaining funding are unverified.
No live model or Telegram requests, webhook registration, deployment or runtime
configuration changes were performed. The prior tunnel 403 was not reproduced;
its current status and deployed revision are unknown. No hackathon credits are
assumed. A live owner run needs a privately configured bot/provider account,
confirmed available funding and approved isolated runtime; new out-of-pocket
charges require owner approval.

## Warp screenshot recovery — November 14, 2026

This post-hackathon increment branches from develop at `5c9a2e8`.
The PR #29 owner retest recorded one provider reservation and an uncertain
provider error without a Telegram result. Issue-note quality and live pricing
were unverified in that run. The retry increment is verified with offline
fixtures.

The Warp launcher uses `warp-extraction-v2` and session-only consent. The
carrier sends one screenshot and sees a processing acknowledgement. Axle makes
a fresh extraction request with the same image after a retryable provider
failure or an unusable extraction response. The private
`warp-retry-pilot.sqlite3` ledger caps the pilot at three provider reservations
across sessions and restarts. Keep that ledger and its owner lock in place.
This ledger belongs to the new pilot and excludes the earlier PR #29 attempt.
Provider reservations are not billing receipts.

Axle rechecks consent and the trip revision before spending. An unavailable
Telegram image prompts a resend without consuming a provider reservation.
An ambiguous request outcome pauses automatic retries. After the cumulative
allowance is exhausted without a usable draft, Telegram offers manual trip
entry with the confirmed profile. The carrier reviews and confirms the current
revision before `/price` computes the result locally.

For an approved live run, use a private real-pilot config whose
`allowed_host` matches the current tunnel. Verify credits cover the remaining
allowance before launching. From the pilot checkout, with the virtual
environment available:

```bash
AXLE_PILOT_CONFIG_FILE=/absolute/path/to/private/warp-config.json \
  PYTHONPATH=src .venv/bin/python -m axle_hackathon.pilot_launch warp
```

Use the same config with `pilot_setup register` and `pilot_setup check`.
Complete teardown with `/forget`, `pilot_setup remove`, and
`pilot_setup check` before stopping the pilot and tunnel. Keep credentials,
raw screenshots and private identifiers out of the test record.

### Live Warp retry pilot result

The Mac pilot ran commit `43a57f03b7da7d4b62bf2df72b060cffeb80daf1`.
Telegram presented the `warp-extraction-v2` disclosure and confirmed the
session-only test profile. One screenshot produced a processing acknowledgement
and a failure reply. The ledger recorded one provider reservation and one
screenshot update with status `uncertain` and category `provider_error`.
The provider outcome and billing are unknown. No automatic retry occurred.
The live run did not reach trip review or pricing. Issue-note completeness
and live retry behavior remain unverified.

Axle acknowledged `/forget` and reported that it cleared the active session.
Telegram reported that the webhook was disabled, with zero pending updates
and no recorded error. The owner confirmed that the pilot and tunnel stopped.

### Inspect extraction failures locally

For future failed uploads, the ledger records the terminal failure stage.
HTTP failures include the response status and a bounded `x-request-id` when
available. The ledger does not establish whether Meta processed or billed a
request. Read the aggregate diagnostics from the Mac before considering another
upload:

```bash
sqlite3 -readonly "$HOME/axle-tomtom-webhook-private/warp-retry-pilot.sqlite3" '
SELECT f.category, d.stage, d.http_status, COUNT(*)
FROM pilot_failure_categories AS f
JOIN pilot_updates AS u USING (update_id)
LEFT JOIN pilot_extraction_failures AS d USING (update_id)
WHERE u.action = "screenshot"
GROUP BY f.category, d.stage, d.http_status;'
```

Share the category, stage, and HTTP status. Keep the request ID local unless it
is needed for a support inquiry. Older entries have no diagnostic details.
