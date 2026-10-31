# H13 Astra boundary review

October 31, 2026. Reviewed draft PR #14 at 14761ab40fd606ca3d9a4477f4fbe15f1dd1944e
using source inspection and offline fault injection. This is an assistant code review,
not an independent security audit or approval to process real carrier data.

## Verdict

Continue offline Meta/Telegram adapter development after these focused fixes. The
current core is not ready to connect real carriers. Authentication, processing terms,
durable delivery and host controls remain concrete release dependencies.

## Reproduced findings and fixes

1. **Failed withdrawal could expose the retained profile after re-consent (high).**
   Inject a SQLite DELETE failure after saving a profile, call forget, then choose
   remember again. Previously that granted access to the undeleted profile. A pending
   deletion now blocks new consent until deletion succeeds. Failed downgrade uses the
   same path. Existing consent is cleared before the attempt. Regression test reproduces
   failure, verifies re-consent remains blocked, repairs storage and verifies absence.
   This latch is process-local. Restart/crash recovery remains a release blocker below.
2. **Closed facade could grant consent again (medium).** After close, remember-mode
   consent could recreate volatile access and sessions even though SQLite was closed.
   Close is now terminal and idempotent; approved operations fail explicitly after close.
3. **Non-ASCII token caused TypeError (low).** Python's string compare_digest rejects
   Unicode. Tokens now require ASCII and exact generated length before comparison;
   invalid tokens produce the intended permission rejection without disturbing valid access.

All three regression tests failed on the reviewed baseline before code was changed.
After fixes: full pytest **243 passed in 2.74s**. Dependency, exported reviewer OpenAPI,
diff and documentation checks are recorded with the PR update. No paid model calls,
carrier records, infrastructure changes, merge or deployment occurred.

## Boundaries checked

The facade resolves approved numeric user/chat pairs before user-triggered database
access, queries profiles by the server-resolved carrier, and checks carrier-scoped
tokens before session work. Rotating consent tokens prevents old integer revisions
authorizing a newly created session. Profile replacement checks the saved version in
a SQLite write transaction. Draft load does not create a confirmed opportunity.
Unknown cost inputs still prevent complete financial acceptance. Session-only flows
do not save profiles; read access does not extend saved-profile expiry.

These properties assume trusted application code. Pure PilotSessions/calculate helpers,
direct SQLite access and Pydantic construction bypasses are not security boundaries.
The future model adapter must never receive these operations as unrestricted tools.
Multiple bindings deliberately mapped to one carrier share consent/state; do not reuse
a carrier key for a different company or infer employee access without owner approval.

## Required before live carriers

- **Durable privacy recovery:** a failed deletion is reported, but an in-memory latch
  cannot survive restart. Persist deletion intent through the durable inbound-command
  design, retry safely before profile access on recovery, and prevent backup restoration
  from reviving withdrawn profiles. A failed request must never be reported successful.
  Until implemented, do not restart/reopen a failed-deletion database for live processing
  without completing the deletion through reviewed recovery. No current automated recovery.
- **Single owner enforcement:** RLock is local to one instance. Two instances/processes
  sharing SQLite can retain divergent consent and a live session after the other forgets.
  Deployment must enforce one owner (or replace volatile grants with coordinated storage).
  SQLite transactions alone do not solve this. The constructor currently does not enforce it.
- **Authenticated transport and paid-work gate:** verify webhook secret, approved sender
  AND private chat before work. Use server-owned callback/task scope, consent token and
  revision; check again before publishing async results. Reject stale completions after
  withdrawal, expiry, changed terms or profile edits. Never trust model-selected identity.
- **Durable deduplication:** persist inbound update IDs and task status before acknowledging;
  replayed consent/save/forget commands and uncertain provider outcomes must not silently
  repeat paid work or overwrite a newer privacy choice. No automatic paid retries.
- **Storage operations:** private directory/file permissions, bounded profile/media sizes,
  safe outward errors/logs, scheduled expiry cleanup, backup policy and owner access
  revocation require implementation and tests. Plain SQLite supplies no encryption here.
- **Actual disclosure/provider review:** the caller-supplied notice is not proof of legal
  consent or account terms. Resolve the observed Meta free-credit product-improvement
  condition before private data. Operational consent grants no secondary research or
  public-evidence permission. The current UI/transport does not collect real consent.

## Next implementation order

Return to Sol Medium for a synthetic-only Meta adapter with scoped inputs and stubbed
provider tests. Add a task-generation check for async completions, then a durable Telegram
inbound queue including privacy-command recovery. Prepare the isolated hosting plan and
re-review the integrated boundaries before any owner-approved real-carrier deployment.
