# H13 execution and shutdown review

October 31, 2026. Baseline draft 2ec1fb9. Assistant source review and offline
fault injection, not an independent audit or live service validation.

## Reproduced fix

Medium: PilotScheduler.close(timeout) called PilotWorker.close before its timed
thread join. Worker.close acquired the inbox lock, so a database operation holding
that lock could block shutdown indefinitely before the timeout was applied.
Worker stop signaling now uses an Event independent of the storage lock. A waiting
tick checks the stop event after acquiring storage and exits before processing.
A baseline regression failed while another thread held the inbox lock; it passes
with the fix. A second test verifies an active blocked tick reports incomplete drain
within the caller's bound, then exits after the lock is released.

The bound relies on the concrete worker's nonblocking close implementation. Arbitrary
injected workers with blocking close are not covered. An already admitted tick can
finish after shutdown is requested; stop does not revoke consent or cancel I/O.

## Integration findings and limits

- Shared worker admission and durable claims prevent overlapping ticks/repeated paid
  attempts through these workers. Lifetime caps are committed before delegation and
  survive restart. Capacity failures intentionally consume reservations; a stalled
  provider can therefore exhaust the remaining caps as later queued tasks are tried.
  This is conservative accounting, but runtime recovery UX must explain it.
- Conversation admission preserves privacy command handling during stalled sends.
  It does not bound pre-admission body readers or socket connections. Database latency
  still blocks the event loop and can delay privacy processing; host admission and
  storage execution policy remain required.
- Scheduler drain reports only its own thread. It can report drained while a provider
  or sender continues after caller timeout. Neither provider nor sender pool exposes
  a public drain result yet. Closing/replacing the inbox must not be based solely on
  scheduler.close returning true. A single lifecycle owner must track all three.
- BoundedDelegator ownership is per wrapper. Constructing another wrapper can create
  capacity while an old timed-out operation remains alive. Live wiring must create
  and retain exactly one provider wrapper per inbox lifetime, just as delivery retains
  its terminal pool. No live launcher exists yet to enforce this composition.
- Timeout means uncertain, not failed/cancelled transmission. Real HTTP deadlines,
  no-retry settings, log sanitization and explicit transport cleanup remain necessary.
  Restoring a database can restore budget counters or withdrawn profiles; backup and
  enrollment/ordering recovery remain separate release gates.

## Next implementation

Build one offline lifecycle owner that creates the inbox, provider wrapper, worker,
scheduler and delivery pool; rejects replacement/restart; stops admission; records
separate scheduler/provider/sender drain state; and retains storage ownership until
safe teardown. Test shutdown after model and sender timeouts before adding real
transport configuration. Preserve privacy handling during normal operation and make
shutdown rejection explicit. Provider data-use terms and isolated hosting approval
remain required before real carrier use.

Validation: 326 tests passed; dependency check, reviewer OpenAPI check and whitespace
check passed. No paid calls, real carrier data, live sends, merge, deployment or
infrastructure changes. This review permits continued offline implementation only.
