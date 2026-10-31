# H13 offline lifecycle owner candidate

Follow-up: [lifecycle ownership review](H13_LIFECYCLE_ASTRA_REVIEW.md).

October 31, 2026. Baseline draft f269086. Injected fake providers/senders and
invented records only; no live launcher, transport configuration or credentials.

PilotLifecycle constructs one inbox, retained provider wrapper, delivery pool,
worker, scheduler and conversation app. Scheduler start is explicit and single-use.
Construction failure closes created resources and releases database ownership.
The owner itself is the ASGI entry point; bypassing it via private app references
or manipulating its component attributes is outside the supported composition.

close(timeout) is synchronous: host shutdown must call it off the event-loop thread.
It closes HTTP admission, signals worker/scheduler stop, closes both executors to
submissions, and reports scheduler/provider/sender/request drain independently.
Executor tracking follows actual Future completion, including work that outlives a
caller timeout. The owner closes the inbox only after all four report drained.
Otherwise it keeps the SQLite connection and exclusive file ownership. Calling
close again can complete teardown after outstanding operations exit. Start remains
rejected after any close attempt. No replacement wrapper is created by the owner.

The timeout bounds scheduler joining; provider/sender/request status checks do not
wait for their work. It is not a hard process termination deadline. Incomplete drain
requires retaining this owner and retrying shutdown status inspection, not reopening
storage. A hung injected operation can therefore intentionally hold ownership and
private arguments indefinitely. Real transport deadlines remain essential. The
owner does not close arbitrary injected transport/client objects, whose lifecycle
must be specified with the real adapters. Standalone helper APIs retain their prior
trusted offline behavior and do not become lifecycle-managed automatically.

During closing all new HTTP requests, including privacy commands, get 503 without
acceptance; normal operation preserves /forget admission as previously tested. An
already admitted request/tick may finish. App lifespan still closes the retained
delivery executor; explicit owner.close is required for complete teardown. Merely
receiving ASGI lifespan shutdown is not yet automatic owner shutdown integration.
There is no live launcher claiming that integration.

Five new cases verify storage stays owned after provider and sender timeouts until
actual exit, terminal restart and HTTP rejection, partial construction cleanup,
and storage retention during an active webhook request. Full suite: 331 tests pass.
Dependency, reviewer OpenAPI compatibility and diff checks pass. No paid calls,
real carrier data, live sends, merge, deployment or infrastructure changes.

Next: integrated review of resource ownership and close races, then wire actual
HTTP/provider deadline settings and host lifecycle handling with fake transports.
Host connection/body-reader bounds, synchronous SQLite latency, provider data-use
terms, controlled enrollment/ordering recovery and backup deletion recovery remain
required before live carrier use. This candidate does not authorize deployment.
