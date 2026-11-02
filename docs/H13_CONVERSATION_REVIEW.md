# H13 synthetic Telegram conversation candidate

Follow-up: [integrated Astra findings](H13_INTEGRATED_REVIEW.md). Conversation values
now share PilotMemory's clear/expiry/close lifecycle; direct withdrawal no longer relies
on transport-specific cleanup. The historical cleanup caveat below is superseded.

October 31, 2026. Based on draft head 4d87ad4. Offline injected transport only;
no live bot, paid request, real carrier input, deployment or infrastructure change.

PilotConversation adds deterministic /start, /reply STEP answer, /confirm STEP,
/edit STEP field value and /save STEP commands. The webhook authenticates and
authorizes the sender/chat before a conversation transition. Each update gets a
durable flow claim before state change or fake send; duplicate delivery cannot
repeat consent, edits, saving or sends. A failed/ambiguous transition/send becomes
uncertain. Raw conversation input and responses are not persisted. After restart
or a lost response, a fresh /start is needed; this is not a durable conversational
transcript or an exactly-once delivery system. Unsupported/stale step responses
are generic 400 responses; final user-facing recovery copy is still needed.

The sequence shows the supplied disclosure and asks session versus remember,
equipment and arrangement first, rental maintenance coverage if applicable, then
three related trip fields at a time, revenue target, and planning CPM or unknown.
Every prompt carries a fresh opaque step code bound to this carrier's current flow.
The underlying consent token stays server-side. Old codes, another carrier's code,
and expired consent cannot confirm or edit current facts. Unknown equipment pauses
intake rather than inventing a unit. Unknown/Skip preserves nullable inputs; payout
and loaded mileage remain required by the current calculator. Update at the equipment
question repeats it. Review-stage corrections support the explicitly listed economic
fields; equipment/arrangement corrections require /start in this first slice.

Cost input deliberately supports only a supplied all-in planning CPM covering all
listed cost categories on ALL operating miles, or unknown costs. The prompt and
review disclose the inclusion assumption and no additions. Itemized intake, rental
allowance tiers, mixed inclusions, and period allocations remain core capabilities
without a conversation adapter yet. No margin, negotiation opening or floor is inferred.
The initial flow marks all inputs synthetic/hypothetical and warns to use invented
figures. This is not a real-data intake switch or private-data provider approval.

Review displays supplied values, unknowns, cost assumptions and a specific revision.
Confirmation is explicit and edits create a new unconfirmed revision. Planning may
remain NEED_MORE_INFORMATION after confirmation when inputs are unknown. Schedule
feasible/conflict is a supplied assertion, not independent routing or HOS clearance.
Required equipment in an offer is never used as a carrier fact.

Remember is storage permission only: /save after confirmation separately persists
the exact profile with saved-version checks. Existing saved versions are checked for
replacement; this flow still asks fresh intake instead of automatically reusing saved
facts. Saved-profile reuse, per-field freshness and adaptive missing-question selection
remain future work. Session mode cannot save. /forget clears the flow and active state
through this webhook and records durable deletion intent through the existing inbox.

Conversation values are volatile and private. Host maintenance must call both
conversation.purge_expired() and inbox.purge_expired(); flow access detects expired
consent and clears its own values. A directly invoked inbox.forget outside this webhook
must also clear the conversation (or run purge) before claiming complete active-state
cleanup. Host shutdown must discard the conversation object. No scheduler/launcher is
installed yet. The injected sender must be bounded, plain text, nonretrying, validate
actual delivery success, and use the server-bound chat destination. Text commands and
step codes are a development interface, not the planned polished button experience.

Validation: assistant Linux, full pytest **290 passed in 3.18s** (279 prior + 11
conversation cases). The full mocked webhook intake-to-evaluation test derives step
codes from the emitted prompts and ends with NEGOTIATE and $300 planning cost for
the invented 240-mile/$420/CPM 1.25 case. Other cases cover corrections/stale confirmation,
unknown inputs, rental coverage, bad answers, scoped codes, duplicates, failed-send
nonreplay, explicit saves, and conversation expiry. No live Meta/Telegram evidence.

Next: review the combined conversation and transport boundaries, then prepare a bounded
runtime launcher, worker scheduling, real sender, paid budgets and isolated hosting plan.
Private-data account terms, command ordering, safe logging, media handling, backup-restore
privacy and integrated Astra review remain release dependencies. No deployment approval
is implied by this offline build.
