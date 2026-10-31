# H13 pilot core — offline implementation

October 31, 2026. Based on design commit 3c1603f. No deployment or paid calls.

Adds an isolated pure Python pilot module; existing synthetic evaluator, routes,
model prompts and reviewer contract are unchanged. This is not yet Telegram or
runtime multi-agent orchestration.

## Implemented
- Frozen validated profile/opportunity snapshots, explicit provenance, no synthetic
  defaults, and itemized versus declared CPM cost modes.
- Decimal calculations over loaded, deadhead and repositioning miles. Rental
  mileage applies to all included miles in this simple supported configuration.
- Complete cost categories or explicit unknowns, CPM inclusion/exclusion checks,
  covered-rental maintenance and duplicate-category rejection.
- Planning reserves kept labeled; totals/surplus are not accounting profit.
- Server-supplied binding map checks every session operation. Profiles remain in
  process memory; returned immutable snapshots cannot change stored confirmations.
- Optimistic revisions and renewed confirmation after every edit, including target
  and profile updates. Synchronous calculation under lock prevents old evaluation
  results overwriting a newer edit. Future asynchronous model work needs its own
  completion revision check before publication.

## Deliberate limits before real use
The trusted adapter must authenticate numeric Telegram IDs and private-chat status;
this module does not authenticate users. Its binding map is not a model tool argument.
There is no endpoint or credential processing here. Session expiry, revocation,
consent workflow, persistence, field-level confirmation timestamps, software status
schema, detailed schedule evaluation, model adapters and webhook dedup remain unbuilt.
No claim of complete hosted tenant isolation follows from these unit tests.

Cost amounts are already normalized carrier-supplied planning allocations. Fuel
price/MPG conversion, period/utilization allocation, rental included-mile allowances,
overage tiers, custom chargeable-mile rules and insurance coverage validation are
not supported yet. Do not translate such agreements into this calculator silently.
Insurance totals must include applicable carrier-confirmed coverages; trailer
interchange is not automatically inferred. Maintenance covered by rental can be
zero/not applicable explicitly; uncovered work requires a separate clarified scope
before the current coverage restriction can be relaxed. Equipment labels are
recorded, not verified capacity/compliance. Schedule is an explicit supplied
assertion, not a routing or HOS check. Supplied CPM inclusions are carrier assertions.

## Validation
Assistant Linux with unchanged requirements.lock.txt in isolated temporary venv:
- Full pytest: 199 passed (183 existing + 16 new).
- pip check: no broken requirements.
- PYTHONPATH=src python scripts/export_reviewer_openapi.py --check: passed.
- git diff --check: passed.

The first OpenAPI command omitted PYTHONPATH and failed to import the package;
the corrected command above passed. Default runtime lacked pytest; tests ran in
an isolated venv after installing the existing lockfile. No dependency change.

Tests cover two scoped carriers/unauthorized binding, stale writes/confirmations,
unknown miles/costs/target/coverage, frozen profiles, schedule decisions, explicit
CPM exclusions, rental mileage/maintenance, reserves, invalid numbers and duplicate
cost rejection. Fixtures are invented test data, not actual carrier records.

Next: expand validated intake cost adapters and metadata, then consent/profile
storage and Meta/Telegram execution. No real-carrier data before those boundaries
are implemented and verified. Merge and deployment remain separate owner decisions.
