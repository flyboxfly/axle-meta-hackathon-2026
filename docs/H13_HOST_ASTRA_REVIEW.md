# H13 host cancellation review

Follow-up: [injected HTTP adapters](H13_TRANSPORT_REVIEW.md).

October 31, 2026. Baseline draft 7541a91. Assistant source review and offline
fault injection; no independent audit or live runtime validation.

Reproduced medium-severity gap: cancelling lifespan while awaiting shutdown left
the host running, HTTP admitted and scheduler active. The regression observed HTTP
404 from the still-running app when shutdown rejection 503 was required.

Lifespan now reserves ownership before its first await. Abnormal exit during
initialization/startup/running immediately closes host admission and attempts owner
cleanup, then re-raises the original exception/cancellation. Shutdown is a retained
Task shielded from caller cancellation. Concurrent inspectors share the active task;
a later inspection after completion can attempt another drain. Task errors are
observed even if waiters disappear. Duplicate lifespan entry is rejected separately
without taking over the existing owner's cleanup.

Three added cases verify cancellation closes admission/resources, caller cancellation
does not cancel or duplicate active shutdown, and startup exceptions are sanitized
while releasing storage. Existing incomplete-drain tests still prove ownership is
retained until actual provider exit. Full suite: 340 tests passed. Dependency,
reviewer OpenAPI and whitespace checks passed.

Limits: shield protects against caller cancellation while the event loop lives. It
cannot prevent process termination, event-loop shutdown cancellation of all tasks,
or loss of a caller's reference to the host. Incomplete shutdown requires an embedding
host that retains this object and inspects drain again. Synchronous startup may outlive
its await; the concrete lifecycle lock/terminal state rejects startup after close.
Arbitrary injected owners/factories do not inherit that guarantee.

HTTP configuration review: explicit phase limits and zero transport retries are
configured, but no SDK retry policy, total network cancellation, provider endpoint,
Telegram sender, sanitized outbound-error boundary or client cleanup is wired yet.
Mock transports verify configuration and call counts, not actual socket timing.
No claim of a hard network deadline follows from these tests.

Next: implement and offline-test the real provider/sender adapters and client ownership
with bounded responses, SDK retries disabled and explicit total-deadline behavior.
Resolve retained-owner process policy, inbound connection limits/SQLite latency,
provider data-use terms, enrollment/order recovery and backup privacy before live use.
No paid calls, real carrier data, live messages, credentials, merge, deployment or
infrastructure changes occurred.
