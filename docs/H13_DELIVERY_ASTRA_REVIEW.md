# H13 delivery and withdrawal review

October 31, 2026. Baseline: draft PR #14 at a8685dc. Assistant source review and
offline fault injection with invented data and fake senders; not an independent
audit or live Telegram evidence.

## Verdict

The reviewed dispatch/withdrawal contract is suitable for the next offline runtime
implementation slice after the two fixes below. It is not clearance to deploy or
process real carrier data. No merge, credentials, paid calls or live sends occurred.

## Reproduced and fixed

1. **Replacement capacity after app shutdown (medium).** Lifespan shutdown closed
   the executor but detached it from its inbox. An already authorized sender could
   still be running while another app/worker created fresh capacity on the same
   inbox. The terminal pool now remains attached. Reusing that inbox cannot reopen
   delivery; shutdown of one app also ends delivery for other apps sharing it.
   A test held a send open across shutdown and reproduced pool replacement before
   the fix. The fix preserves the same pool and rejects further submission.
2. **Cancelled webhook left delivery eligible (medium).** asyncio cancellation
   bypassed the ordinary exception handler. An accepted flow stayed processing;
   work already handed to another thread could later authorize delivery. The handler
   now records uncertain and propagates cancellation. A test cancels the request
   before dispatch and then runs the captured pending work: its durable guard rejects
   it and the sender is not invoked. If dispatch already won the state-lock race,
   cancellation cannot retract that authorized send. Storage failure can prevent the
   status write; there is no stronger guarantee under failed storage.

Both new regression tests failed on baseline and passed after the fix.

## Confirmed boundaries

- Withdrawal before the dispatch guard prevents sender invocation. The guard checks
  current consent/revision or conversation nonce, and changes processing to sending
  under the same inbox lock. A new event-controlled test proves this for evaluation.
- Withdrawal after authorization completes without waiting for sender I/O. An already
  authorized send may still arrive. Authorization is the boundary, not the instant
  a socket transmits: thread scheduling can put invocation after withdrawal returns.
- Caller timeout marks the task uncertain, keeps capacity occupied until actual sender
  exit, and does not retry. New evidence verifies late sender success cannot restore
  completed status. Restart recovery now explicitly tests both processing and sending.
- Refresh restores the current prompt without repeating confirmation, persistence or
  paid evaluation. This remains a development command interface, not final intake UX.

## Remaining work before a live runtime

- Implement bounded request/worker admission, expiry maintenance and queue scheduling.
  asyncio.to_thread has no application-level request admission bound; SQLite operations
  still run on the event loop. Two sender slots alone do not bound the whole service.
- Implement an injected HTTP sender with actual connect/read/total deadlines and no
  automatic retries, plus provider deadlines, global/per-carrier paid budgets and
  shutdown/drain policy. Python cannot cancel a running sender thread. Closed inbox
  ownership/replacement and process restarts must not be treated as proof that old
  external requests stopped; the pool bound is per inbox, not cross-process.
- Preserve durable single-attempt claims. Surface unknown delivery outcomes without
  claiming failed delivery or automatically repeating paid work. Decide how unsupported
  authenticated updates are acknowledged so poison updates do not retry indefinitely.
- Resolve provider data-use terms, operational disclosures, controlled tester enrollment
  and message-order recovery, private storage/logging, and backup-restoration deletion.
  Current synthetic labels do not prevent a person from typing private information.
- Prepare isolated hosting and owner smoke-test instructions before seeking deployment
  approval. Existing shared-proxy, production and infrastructure holds remain in force.

Validation: **310 tests passed in 4.33s** (305 prior plus five cases). Dependency
check, reviewer OpenAPI compatibility check and git diff whitespace check passed.

Next implementation slice: offline runtime controls with injected transports and clock,
explicit admission/budget/deadline behavior, scheduler and shutdown tests. Keep real-data
processing disabled. Review that concrete candidate before any live configuration.
