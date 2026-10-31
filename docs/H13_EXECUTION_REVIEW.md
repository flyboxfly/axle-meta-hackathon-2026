# H13 bounded execution and scheduler candidate

October 31, 2026. Baseline draft f83b793. Offline fake providers/senders only.

BoundedDelegator wraps an injected delegator with one in-flight operation and an
explicit finite positive caller timeout. No queue or retry is created. A timed-out
operation retains capacity until actual exit, its task becomes uncertain, and its
late result cannot reach delivery. Capacity failures still consume a worker attempt
reservation: caps deliberately count attempts rather than measured billable calls.
Close is terminal for submissions. This bounds caller waiting; it does not terminate
Python threads or enforce a socket deadline. Real HTTP connect/read/total deadlines
and retry disabling remain required. A hung provider can retain private arguments
and an executor thread until actual exit, including during shutdown.

PilotScheduler starts only through explicit start(), runs one synchronous tick at a
time on its own thread, and waits an explicit interval after every tick. Idle waits
are interruptible. Exceptions produce only an unavailable status, then wait before
another tick; durable task claims still prevent replay of uncertain paid work.
close stops new iterations, closes worker admission, waits a bounded duration and
returns whether its thread drained. An admitted tick may finish after close. A false
return means incomplete drain; it is not permission to release/reopen storage or
replace a provider pool. Start/close cannot restart the same scheduler. No scheduler
is attached to an app or launched by importing this module.

Conversation webhook work now has two nonblocking slots shared across apps using one
inbox. Saturated flow requests return 503 before mutation/admission; they have not
been accepted and may be delivered again. Slots are released on success, failure or
cancellation. Evaluation metadata and /forget do not consume those slots, preserving
privacy admission during stalled reply sends. This limits conversation dispatch
waiting, not total inbound connections/body readers. The existing body timeout/size
checks still apply. Host connection limits and SQLite latency controls remain needed;
SQLite work is still synchronous on the webhook event-loop thread.

Nine new cases test provider timeout/retained capacity/late-result suppression,
scheduler idle stop, incomplete drain and terminal restart behavior, invalid wait
configuration, and simultaneous saturated conversations with successful forget.
Full suite: **324 passed in 3.73s**. pip check, reviewer OpenAPI compatibility and
diff whitespace checks passed. No paid calls, credentials, real records, live sends,
merge, deployment or infrastructure changes.

Next: review the integrated ownership, shutdown and admission boundaries before
wiring real transports. Actual HTTP client configuration and scheduler lifespan
integration remain unimplemented. Provider data-use clearance, private storage/log
policy, controlled enrollment/message ordering recovery and backup deletion recovery
remain live-use gates. These modules do not enable real-data processing.
