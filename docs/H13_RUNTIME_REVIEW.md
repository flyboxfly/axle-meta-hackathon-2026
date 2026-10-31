# H13 offline worker and attempt caps

Follow-up: [bounded execution and scheduler](H13_EXECUTION_REVIEW.md).

October 31, 2026. Based on draft PR #14 at 1a80374. Invented records and injected
fake providers/senders only. No launcher, credentials, live requests or deployment.

PilotWorker.tick performs expiry cleanup, services pending privacy records first,
and attempts at most one queued evaluation. Host code must supply scheduling; this
module does not start background threads or install a runtime. All workers sharing
one inbox share a nonblocking worker lock. A second tick returns busy without paid
work. Existing durable evaluation claims prevent replay. Stale/unconsented queue
items become uncertain so they do not indefinitely block later items.

Explicit positive global and per-carrier attempt caps are required. Reservations
are committed in the owning SQLite database before calling the injected delegator.
Failures consume reservations; no automatic refund, retry, daily reset or counter
pruning exists. Counters survive worker/inbox restart and withdrawal. These are
lifetime attempt caps for this database, not dollar budgets or billing measurements.
Changing configured caps changes allowed totals and must be an owner runtime choice.
Deleting/restoring the database can erase counters; backup policy remains unresolved.
No identity, raw opportunity, consent token or result is persisted in budget rows.

close prevents subsequent ticks on that worker. An already admitted tick can finish;
close does not cancel provider or sender I/O. Inbox shutdown still closes delivery
and clears authorization. This is not a complete drain policy. Existing direct
run_evaluation/PilotDelegator helpers remain trusted offline APIs and do not enforce
these caps by themselves; a future launcher must route every paid attempt through
the reviewed worker boundary. There is no live launcher to bypass here.

Evidence: five new tests cover durable caps across restart, shared global caps across
two carriers, consumed failed reservations/no retry, shared worker admission plus
close, and privacy processing after budget exhaustion. Full suite: 315 passing tests.
Dependency and reviewer OpenAPI checks pass.

Remaining before runtime: bounded webhook/request admission that preserves privacy
handling, actual HTTP/provider connect/read/total deadlines with retries disabled,
host scheduler/backoff and shutdown drain policy, budget failure recovery UX, transport
integration, provider data-use terms, controlled enrollment/ordering recovery and
backup-restoration privacy. The worker tick is synchronous and must not be called on
the async webhook's event-loop thread. No live-readiness clearance follows.
