# H13 privacy acknowledgement review

November 2, 2026. Baseline e19cb8b. Offline assistant review, not independent audit.
No new production-code defect identified in this focused review. Added tests for
previously unexercised dispatch supersession and failure boundaries.

Withdrawal and durable deletion intent precede acknowledgement dispatch. Reply copy
says deletion requested, not completed; external histories are explicitly separate.
Worker deletion does not depend on a successful send. Duplicate updates return without
another acknowledgement. The privacy path does not acquire conversation flow slots.
The existing sender pool bounds actual in-flight attempts, retains capacity after a
caller timeout, and participates in lifecycle drain before storage release.

The guard checks the latest privacy update and absence of active consent under the
inbox lock immediately before dispatch. Tests now verify suppression after fresh
consent and after a newer privacy request. This check is an authorization boundary,
not a recall mechanism: later consent changes cannot retract an already authorized
send. An acknowledgement is only a historical statement about the withdrawal request.

Additional tests verify full sender capacity cannot prevent durable withdrawal;
a timed-out sender remains tracked while deletion completes; and cancellation during
acknowledgement preserves withdrawal and duplicate suppression. The cancellation test
covers interruption before actual thread dispatch. Existing delivery/lifecycle tests
cover retained real work and storage ownership. No claim of a durable acknowledgement
outbox, exactly-once external delivery, or guaranteed receipt is made.

A timeout, saturated pool or interrupted request can still produce silence. This is
acceptable for the current best-effort acknowledgement because it does not weaken
withdrawal; stronger user-facing status/recovery would require separate implementation.
No raw carrier facts or identifiers are included in the acknowledgement. It never
invokes the model or increases the model-attempt budget.

The owner-operated live evidence remains pinned to d2d2906, before acknowledgement
support. No new live evaluation is necessary to establish these offline properties.
A later authorized privacy-only smoke test may verify the visible reply without a
model call. Merge and any restart/redeployment still require owner approval.

Next step: final PR integration/mergeability review, then a concrete merge request.
No repeated model-switch loop is needed for this acknowledgement slice. Private test
config/state retirement and provider-credit reconciliation remain owner closeout items.

Validation: 391 offline tests passed in 11.38s, including five new review cases.
Dependency check, reviewer OpenAPI check and whitespace checks passed. Production
source unchanged in this review; no live sends, model calls or infrastructure changes.
