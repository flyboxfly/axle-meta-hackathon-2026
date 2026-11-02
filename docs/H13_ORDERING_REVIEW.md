# H13 conservative private-chat command ordering

October 31, 2026. Baseline 1477e8c. Offline candidate, not live Telegram evidence.

Authenticated supported webhook commands now require a positive signed-64-bit
message_id. A persistent pilot_message_order row per approved carrier/user/chat
records the highest admitted message ID. Known updates retain duplicate handling;
previously unseen messages at or below that fence return 200 stale without mutating
conversation, consent, profile, queue work or deletion intent. No private answer is sent.

Flow claims, evaluation queue admissions and privacy admissions record their ordering
fence in the same SQLite transaction as the durable admission. A failed admission
rolls back the fence; an admitted transition that subsequently fails validation/delivery
remains consumed and requires a newer user command. The ordinary queue capacity check
still does not prevent the separate bounded privacy admission path.

This is a conservative fail-closed policy based on per-chat message-ID progression,
not update-ID progression. Update IDs can reset independently; a fresh higher message
ID can be accepted with a lower unused update ID. Ordering fences persist across
restart and are not reset by /start, withdrawal, re-consent or session expiry. They
contain private operational identity metadata, not text. Historical ordinary update
records remain retained for their original deduplication checks.

There is no reorder buffer: a late legitimate message is rejected rather than executed
out of sequence. Do not claim complete Telegram sequencing guarantees from this local
policy. Chat history changes, message-ID reset/reuse, binding reassignment and sequence
recovery need an owner-reviewed epoch procedure before live use; never reset a fence
automatically because a lower ID arrives. The first admitted command establishes the
baseline; existing development databases cannot reconstruct message order for earlier
rows that never recorded message IDs. Plan controlled clean enrollment and pending-update
handling before first registration; no webhook registration setting was changed here.

The webhook factory now rejects multiple approved bindings mapped to one carrier.
The core can still represent them for trusted offline work, but independent chat order
cannot safely coordinate multiple operators sharing live carrier state. Multi-operator
access needs a separate coordinated policy. The initial pilot supports one approved
private chat per carrier; server IDs remain outside model arguments.

Internal direct begin_flow/submit calls keep an optional message_id for existing offline
tests. Only the webhook's validated path provides this ordering guarantee. Model tools
must not call those internal operations or choose message metadata.

Validation: **302 pytest tests passed in 3.48s** (297 prior + 5 ordering cases).
Cases cover delayed unseen start/forget, restart, lower update IDs with newer messages,
ordinary-capacity failure without fence advancement, privacy admission under capacity,
and rejection of shared-carrier chat configuration. Existing duplicate, privacy recovery
and mocked end-to-end conversation/evaluation tests also pass. No live messages or paid calls.

This addresses the cross-command delay case for the supported candidate ordering policy.
Blocking sends/global-lock occupancy and missing user-facing recovery remain open from
the integrated review. Next: separate bounded delivery execution from state mutation,
then safe refresh/error recovery, runtime budgets/wiring and integrated re-review.
