# H13 bounded delivery and conversation recovery candidate

October 31, 2026. Based on draft c308ab6. Offline fake senders only; no Telegram
client, bot credentials, paid requests, deployment or infrastructure changes.

State mutation and canonical evaluation remain under the owning memory lock. Actual
injected send now executes outside that lock. Conversation webhook delivery waits
through asyncio.to_thread, so its network wait no longer runs on the event-loop thread.
Synchronous SQLite work remains in the handler; storage latency and request admission
limits still need runtime controls. This is not a final background task scheduler.

One shared DeliveryPool per inbox bounds external attempts to two slots with a
five-second caller wait. Pool capacity is nonblocking. A dispatch guard rechecks the
current conversation nonce/consent or evaluation revision and commits a sending marker
before releasing the state lock for the actual send. Late state changes before guard
execution reject the attempt. Once dispatch is authorized, the external send is in
flight and later withdrawal cannot recall it. This explicit boundary replaces holding
the entire privacy/state lock during network I/O.

Timeout means uncertain, not cancellation. The underlying sender can continue; its
slot stays occupied until it returns. No automatic retry or replacement attempt is
created. A late completion cannot turn an already uncertain task back into completed.
Restart marks both processing and sending records uncertain. Inbox close/app lifespan
closes the shared pool to new submissions without blocking on ongoing I/O. Python
threads cannot forcibly terminate hung network calls; real HTTP connect/read/total
deadlines and SDK retry disabling are still mandatory before runtime use. A genuinely
hung injected sender can retain threads through shutdown; tests use bounded events.

Conversation validation errors now produce bounded, generic carrier-facing guidance
and the current prompt when authorized. Raw answers and exception details are excluded.
/refresh returns the current prompt with its existing step code; it does not repeat
the previous mutation, confirmation, save or evaluation. Expired/missing state gets a
fresh-start instruction. Known updates still are not replayed. A carrier who lost an
ambiguous prompt can send a NEW /refresh command; there is no automatic message retry.
The current prompt is kept in private volatile conversation state and shares core
withdrawal/expiry/close cleanup. It is not persisted in the inbox.

Tests: **305 passed in 3.58s** (302 prior + 3 delivery/recovery cases). New evidence
includes withdrawal completing during a deliberately stalled evaluation send, timeout
capacity remaining occupied until underlying exit, and safe invalid-answer guidance/
refresh without mutation. The prior full synthetic webhook intake-to-mocked-model flow
continues to pass. No live delivery/reliability evidence.

Remaining: integrated review of dispatch/withdrawal semantics, enforced HTTP deadlines,
global/per-carrier paid budgets and request limits, worker scheduling, real sender,
private-data terms, controlled enrollment/ordering recovery, backup-restore privacy and
isolated hosting preparation. Existing review blockers are addressed only to the scope
described here; no approval for real-carrier runtime follows.
