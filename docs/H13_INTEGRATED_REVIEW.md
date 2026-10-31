# H13 integrated Astra review

October 31, 2026. Baseline: draft PR #14 at 7c1993e. Assistant source review and
offline fault injection; not an independent audit or live service validation.

## Verdict

Continue offline development. Do not enable the runtime for carriers yet. The
conversation cleanup fix below is complete; queue-pressure privacy, command ordering,
recovery UX and runtime concurrency controls still require implementation.

## Fixed: conversation values outlived core cleanup (high)

Direct memory.forget, memory expiry maintenance, and memory.close cleared session
objects but retained the separately owned conversation values and consent token.
The webhook's explicit cleanup masked this in its happy path. Three new regression
tests failed on the baseline. Conversation state now belongs to PilotMemory and is
removed through the same clear/expiry/close lifecycle. Newly acknowledged consent
explicitly installs only the new flow after prior state is cleared. Pending disclosure
expiry also removes its pre-consent flow.

Full suite after fix: **293 passed in 3.06s**. The existing webhook intake-to-mocked
evaluation test still passes. No paid calls, private carrier data, deployment or merge.

## Open release blockers

1. **Privacy command at queue capacity (high, reproduced).** Filled a temporary inbox
   with 10,000 invented completed metadata rows; submit(forget) raised capacity error
   and the old confirmed session remained usable. The command is not acknowledged as
   accepted, but active processing should stop even under queue pressure. Implement a
   bounded durable privacy-command admission/recovery path that also preserves dedup
   and cannot let an old retry erase newly saved state. Do not simply prune dedup IDs
   or exempt unlimited commands from capacity limits. Test crash and retry boundaries.
2. **Command ordering (high, inspection).** Dedup handles repeated IDs, not delayed
   previously unseen commands. /start and /forget have no session/step generation;
   delayed old delivery can reset or withdraw a newer session. Define ordering using
   authenticated message metadata and a persisted policy, accounting for Telegram's
   update-ID reset behavior after inactivity. Step nonces already protect reply/edit/
   confirm; they do not solve this separate case.
3. **Blocking request/delivery path (medium, inspection).** Synchronous SQLite work
   and injected send run directly in the async webhook, often holding the global memory
   lock. A slow real sender can block webhook handling, including withdrawal. Move
   accepted work to a bounded worker arrangement and enforce sender/provider deadlines;
   preserve consent/revision checks at delivery and explicit uncertain outcomes. Do not
   infer safety from mocked instantaneous sends.
4. **Invisible validation/recovery failures (medium, inspection).** Invalid/stale intake
   receives generic HTTP 400, not a carrier-facing explanation. Telegram may retry;
   the durable duplicate then gets 200 without a replacement prompt. A failed prompt
   send can similarly leave an advanced step the carrier never saw. Add bounded safe
   recovery replies or a refresh flow without replaying mutations, saves or paid work.
5. **Live runtime dependencies remain.** No scheduler, real sender, durable paid budget,
   final logging policy, private-data provider clearance or deployment plan is present.
   Source labels alone cannot prove typed free text is synthetic. Keep tests invented.
   Backup restoration may reintroduce withdrawn profiles and needs a reviewed policy.

## Positive boundaries and limits

The authenticated webhook checks the secret before reading its bounded body and then
checks private sender/chat against server bindings. Conversation updates are claimed
before mutations; repeated IDs do not repeat effects. Step codes are carrier-scoped,
edits invalidate confirmation, and saving is explicit after confirmation. Evaluation
claims are single-use, abandoned processing becomes uncertain, and both model completion
and delivery recheck consent/revision. Canonical economics stays outside model control.
File ownership enforcement and durable deletion intent improve restart behavior, but
do not resolve queue overload or backup restores. No live security guarantee follows.

Next: use Sol Medium to implement and test the open privacy/ordering/recovery controls,
then prepare runtime wiring. Re-review those integrated changes before requesting any
owner deployment approval. Existing protected infrastructure holds continue to apply.
