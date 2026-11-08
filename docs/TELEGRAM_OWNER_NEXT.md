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
