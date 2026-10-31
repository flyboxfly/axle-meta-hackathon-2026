# H13 host lifespan and HTTP configuration candidate

October 31, 2026. Baseline draft 01b7239. Offline fake transports only.

PilotHost is an explicit ASGI adapter around one PilotLifecycle. It rejects HTTP
before successful startup and once shutdown begins. Lifespan startup starts the
owner's scheduler off the event loop. Shutdown also calls the owner off-loop and
reports complete only if every drain field is true. Otherwise it reports shutdown
failed, raises a fixed error, and retains the owner. finish_shutdown can inspect
again after outstanding work exits without constructing replacement resources.
Repeated startup is rejected. Startup exceptions produce fixed failure text and
attempt cleanup. The host does not forward lifespan to the inner conversation app:
the owner now performs complete resource teardown instead of delivery-only closure.

The host adapter must be retained by its embedding process on incomplete shutdown.
Reporting ASGI shutdown failure cannot force a server/process manager to keep the
process alive. Host termination policy remains a deployment concern. Abrupt task
cancellation/disconnection of the lifespan coroutine is not yet covered by tests;
no hard cancellation guarantee is claimed. TestClient failure handling required
raising after failed lifespan messages, consistent with its installed implementation.

create_http_client configures finite positive connect/read/write/pool timeouts,
one or two connections, zero HTTPTransport retries, disabled redirects and no
ambient proxy/environment configuration. Construction makes no requests. These
are phase/inactivity limits, not a hard total request deadline: a response sending
chunks can outlive the caller's total wait. Existing bounded execution wrappers
still retain slots/ownership until actual exit. Model SDK-level retries must also
be disabled when wiring the provider; this factory alone does not control SDK retries.
Sources checked: https://www.python-httpx.org/advanced/timeouts/ and
https://www.python-httpx.org/advanced/transports/ (October 31, 2026).

The generic HTTP factory is not yet wired to a Telegram sender or provider client.
No credential loader, endpoint launcher, webhook registration or live call is added.
Client cleanup must be connected only after owned operations drain; currently the
caller owns the returned client/context manager. Do not log raw HTTP exceptions or
secret-bearing URLs; production adapters must sanitize them.

Five new cases cover clean host start/stop, incomplete shutdown and later completion,
responsive HTTP rejection during off-loop shutdown, explicit phase-limit/no-redirect
configuration and one-attempt timeout propagation through a mock transport.
Full suite: 337 tests pass. Dependency, reviewer OpenAPI and diff checks pass.
No paid calls, credentials, real carrier data, live sends, merge, deployment or
infrastructure changes.

Next review: lifespan cancellation/startup failure cleanup and retained-owner hosting
policy. Then implement provider SDK and Telegram sender wiring with fake transports,
including actual total-deadline policy, sanitized errors and client cleanup. Host
connection/body limits, SQLite latency, provider data-use clearance, enrollment/order
recovery and backup deletion policy remain live-use gates.
