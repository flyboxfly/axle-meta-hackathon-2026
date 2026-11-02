# H13 pilot core — offline implementation

October 31, 2026. Initial core based on design commit 3c1603f; normalization slice
based on GitHub-verified draft head acb03c6. No deployment or paid calls.

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
- Explicit cost methods: per-mile, per-trip, per-hour, period allocation, or fuel
  price per US gallon / miles per US gallon. Fuel applies to all operating miles.
  Hourly costs require supplied total trip hours, including applicable dwell/handling.
  Weekly/monthly/yearly allocations require cost and utilization periods to match;
  missing utilization stays unresolved. No automatic calendar conversion or mileage forecast.
  Original amounts, source and allocation/fuel inputs remain in the frozen profile.
  Intermediate arithmetic is not rounded to CPM; displayed money rounds to cents.
- Results identify calculator pilot-v2, itemized cost breakdown and a separate
  declared-CPM component. Separately rounded lines may differ slightly from total.
  Known component estimates may appear with an unresolved total; they do not establish
  cost completeness, applicability or independently verified rental/insurance terms.
- Optional unit/role metadata with timezone-aware effective/recorded times; optional
  effective time per cost. Software records distinguish subscribed/planned/interested
  with source. These supplied facts grant no integration access or processing consent.
- Session confirmation records server UTC time for the entire revision. Edits reset
  confirmation and its timestamp; this is not per-field confirmation or freshness enforcement.
- Server-supplied binding map checks every session operation. Profiles remain in
  process memory; returned immutable snapshots cannot change stored confirmations.
- Optimistic revisions and renewed confirmation after every edit, including target
  and profile updates. Synchronous calculation under lock prevents old evaluation
  results overwriting a newer edit. Future asynchronous model work needs its own
  completion revision check before publication.

## Deliberate limits before real use
The trusted adapter must authenticate numeric Telegram IDs and private-chat status;
this module does not authenticate users. Its binding map is not a model tool argument.
There is no endpoint or credential processing here. The separate [memory facade](H13_MEMORY_REVIEW.md)
now adds offline consent gating, session access expiry, withdrawal and explicit profile
persistence. The pure PilotSessions helper itself has none of those policies; future
transport must use the facade. Field-level confirmation timestamps, freshness policy,
detailed schedule evaluation, model adapters and webhook dedup remain unbuilt.
No claim of complete hosted tenant isolation follows from these unit tests.

Cost amounts and assumptions are carrier-supplied planning inputs. Period allocation
is amount * trip operating miles / supplied operating miles in the same period;
it is a utilization-based planning share, not a rental invoice or duration-based charge.
Rental included-mile allowances, overage tiers, custom chargeable-mile rules, differing
labor-hour bases within one trip, and insurance coverage validation remain unsupported.
Do not translate such agreements into this calculator silently.
Insurance totals must include applicable carrier-confirmed coverages; trailer
interchange is not automatically inferred. Maintenance covered by rental can be
zero/not applicable explicitly; uncovered work requires a separate clarified scope
before the current coverage restriction can be relaxed. Equipment labels are
recorded, not verified capacity/compliance. Schedule is an explicit supplied
assertion, not a routing or HOS check. Supplied CPM inclusions are carrier assertions.

The offline pilot software field now requires structured records instead of strings;
no persisted profiles or deployed consumers existed at that slice to migrate. Synthetic contracts
and dependencies are unchanged. Direct calculate(Snapshot(..., confirmed=True)) remains
a trusted offline helper; a timestamp or metadata alone never authenticates a carrier.

## Initial core validation
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

## Normalization slice validation
Assistant Linux, October 31, 2026, same isolated venv and unchanged lock:
- Focused initial run: 35 passed; subsequently added weekly-rental allocation case.
- Final full pytest: 219 passed in 2.97s (183 original + 16 initial pilot + 20 normalization).
- pip check: no broken requirements.
- PYTHONPATH=src python scripts/export_reviewer_openapi.py --check: passed.
- git diff --check: passed.

New cases exercise whole-trip fuel/hourly/period costs, missing versus zero inputs,
weekly/monthly/yearly utilization, incompatible periods, ambiguous cost methods,
invalid numbers, rounding, separate rental base/mileage/covered maintenance,
CPM inclusion overlap, metadata/software validation, and confirmation invalidation.
All fixtures are invented; no live bot, provider call, carrier data or hosting was tested.

Next: Meta/Telegram execution and release-boundary review. No real-carrier data before those boundaries
are implemented and verified. Merge and deployment remain separate owner decisions.
