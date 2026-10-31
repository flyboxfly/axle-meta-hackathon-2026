# H13 privacy admission under queue pressure

October 31, 2026. Based on draft head 3d2e22d. Offline fix for the reproduced
full-inbox withdrawal failure. No runtime, paid inference, live data or deployment.

Forget now uses pilot_privacy, with at most one current record per approved numeric
user/chat binding, separate from the 10,000 ordinary update records. Each accepted
command replaces that binding's privacy record and atomically writes deletion intent.
The table retains carrier, numeric IDs, latest privacy message/update IDs and status;
this is private operational metadata. It is not raw message or conversation storage.

Active consent, session/results and conversation values are cleared before attempting
the write. If storage fails, no success is acknowledged; the in-process pending deletion
latch blocks further consent until deletion succeeds. If storage cannot record anything,
there is no durable acceptance guarantee across crash. Host recovery must handle that
failure before reopening private profile access. Existing backup-restoration hold remains.

Webhook forget requires a positive integer Telegram message_id. The privacy watermark
uses message IDs within the bound chat rather than relying on globally increasing update
IDs across long inactivity. Repeated or lower privacy message IDs are conservatively
suppressed. This is a fail-closed candidate ordering rule, not proof of complete Telegram
ordering semantics. General command ordering and reset/recovery policy remain unresolved.
Direct offline submit defaults command_id to update_id for test compatibility; a live
transport must always pass the validated message ID. Do not clear/reuse watermarks to
recover service without a reviewed epoch/ownership policy.

The current privacy update cannot be reused by another binding. Ordinary duplicate
updates retain their existing checks. Re-consent completes pending deletion before
access; if it already did so, processing the retained privacy worker record only marks
it complete and does not delete a newer saved profile. Superseded worker IDs cannot
execute the latest privacy record. No pruning of ordinary dedup records was introduced.

This closes the queue-capacity admission gap only. A delayed unseen forget newer than
the previous privacy watermark can still arrive after a newer start/consent command.
Implement general cross-command ordering before live use. Synchronous sends, recovery
UX, paid budgets, scheduler/launcher and provider data conditions are also still open.

Tests add full-capacity withdrawal without queue growth, restart/re-consent and stale
privacy suppression, lower update-ID independence, bounded repeated privacy records,
cross-binding conflicts and storage-failure withdrawal without false acknowledgement.
All records are invented. Final full pytest: **297 passed in 3.73s** (293 prior + 4
new cases). pip check, exported reviewer OpenAPI compatibility and diff checks passed.
