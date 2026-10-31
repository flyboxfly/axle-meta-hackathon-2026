# H13 lifecycle ownership review

October 31, 2026. Baseline draft 65b6fc1. Assistant review and offline fault
injection; not an independent audit or live runtime validation.

## Reproduced and fixed

Medium: close held the lifecycle admission lock across scheduler join, executor
shutdown and storage close. The async HTTP entry point synchronously acquired that
same lock. While shutdown waited on a scheduler, even a request intended to receive
503 could block the event loop; admitted requests also could not finish accounting.

A separate nonblocking close lock now serializes teardown. Admission uses its short
lock only to mark closing; scheduler joining and resource cleanup run outside it.
Concurrent close attempts raise a fixed Shutdown already in progress error without
waiting; callers can inspect again after the active close returns. A deterministic
regression stalled scheduler.close and reproduced delayed HTTP rejection on baseline.
After the fix the request receives 503 while shutdown remains stalled, and concurrent
close rejection is also checked.

## Reviewed invariants

HTTP admission and request accounting are atomic under their short lock. Once closing
is marked, no new request increments the count. Executor shutdown prevents later
successful submissions; actual Future completion, not caller timeout, drives drain.
The scheduler must drain and all admitted requests finish before storage is released.
Provider and sender tracking independently preserve ownership for late operations.
Existing tests prove file ownership is retained until late provider/sender exit and
that partial construction releases resources for a later owner.

This reasoning covers the supported owner entry point and owned scheduler. Calling
worker.tick directly on another thread, accessing the private app, closing the inbox
manually, or constructing replacement wrappers bypasses that composition. Runtime
wiring must expose only the owner, create resources once, and keep injected factories
free of background work during construction. Injected transports are still responsible
for their own HTTP deadlines, retry settings and eventual cleanup.

## Next step and remaining gates

Proceed with an offline-tested host lifespan adapter and real transport configuration.
The host must run synchronous close off the event loop, inspect all drain fields,
retain the owner on incomplete drain, and close transport clients only after their
operations finish. ASGI lifespan shutdown currently closes delivery only; it does
not yet invoke owner.close. Do not mistake server shutdown completion for full drain.

Actual network deadlines, no-retry enforcement, bounded inbound connections/body
readers, SQLite event-loop latency, provider data-use clearance, enrollment/message
ordering recovery and backup deletion recovery remain live-use gates. No deployment
or real-carrier clearance follows from this review.

Validation: **332 tests passed**; dependency check, reviewer OpenAPI compatibility
and whitespace checks passed. Fake providers/senders and invented records only.
No paid calls, credentials, live messages, merge, deployment or infrastructure changes.
