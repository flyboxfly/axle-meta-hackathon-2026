# Axle synthetic freight evaluation — reviewer API documentation

Operator: Fly Box Fly LLC. Support/privacy: contact@flyboxfly.com.
Product: https://axle.flyboxfly.com · [Privacy](https://axle.flyboxfly.com/privacy)
· [Terms](https://axle.flyboxfly.com/terms).

This is a synthetic hackathon service, separate from the product website's
real beta inquiry form. Native Muse connection, bearer compatibility within
Muse, secure reviewer credential delivery, and approval remain unverified.
The observed submission portal offers Raw API and Existing MCP; this proposal
uses Raw API. There is no MCP server or OAuth implementation.

## Endpoint and scope

Base: `https://axle-api-demo.flyboxfly.com`.

| Method | Endpoint | Authorization | Outcome |
|---|---|---|---|
| GET | `/api/health` | None | `{"status":"ok","synthetic_only":true}` |
| POST | `/api/v1/axle/evaluate` | Bearer | Canonical evaluation and missing-fact questions |

Only these two public routes exist. `/`, `/docs`, `/redoc`, `/openapi.json`,
browser and model routes are disabled on this service. The static
[OpenAPI 3.1 document](openapi.json) documents the contract; it does not enable
a runtime route. Generate it with
`PYTHONPATH=src python scripts/export_reviewer_openapi.py`.

Proposed tool: `evaluate_confirmed_freight_opportunity`, **Read**, not a
sensitive write, subject to Meta classification. POST computes a result without
changing account or freight state. No booking, negotiation messages, payment,
carrier identity lookup, database writes, file writes, screenshot intake,
model inference or background jobs. In-memory quota timestamps are retained
until expiry/restart; infrastructure may log metadata.

Value beyond browsing: an agent can delegate exact decimal economics to a
specialized service, preserve confirmed carrier requirements, and retrieve
structured next questions without substituting model arithmetic.

## Authentication and permissions

Use HTTPS with normal certificate verification. Inject a privately provisioned
credential as `Authorization: Bearer <private credential>` on the server side.
Never put a credential in model arguments, prompts, tool output, public docs,
URLs, screenshots, ordinary submission fields, commits, analytics or logs.
Do not forward browser Basic authorization or an `Origin` header.

The current demo accepts one service-wide token, not per-user identities,
OAuth scopes, self-service accounts, plans or refresh tokens. It grants only
synthetic evaluation. A health success does not verify evaluation authorization.
Missing/wrong credentials return 401. Revocation/rotation requires an owner
runtime change and process restart; it has not been drilled. A dedicated
reviewer credential has not been issued. Do not give reviewers the owner's
existing token as a shortcut.

Credential handoff is **blocked pending a verified secure portal/reviewer flow**.
Meta's [guidelines](https://platform.muse.ai/docs), sections 5 and 5.4–5.5,
request integration/test credentials through secure instructions. Neither those
guidelines nor the supplied Technical specs screenshot specifies the actual
secret-entry mechanism or confirms custom Authorization-header support.
Review any credential UI before entering a value. Do not request a new key,
rotate the deployed token, or provision account access without owner authorization.

## Inputs and confirmation

Request JSON must contain `opportunity`, `benchmark`, `facts_confirmed: true`,
and `source` (`manual` or `screenshot`). Unknown costs remain null/omitted;
unknown is not zero. Unknown revenue target is explicitly null, with
`benchmark.confirmed: true`. Both confirmation fields require actual JSON
booleans, and must be true. Extra request properties are rejected.

The caller must obtain carrier review of facts and target choice before
asserting confirmation. The API trusts caller assertions; it does not prove
human identity, review, screenshots, mileage, or legal schedule feasibility.
Changed facts/requirements require renewed review. The model cannot supply
or infer consent. Muse permissions do not replace carrier fact confirmation.

| Opportunity field | Meaning / validation |
|---|---|
| `equipment` | Required enum; see below |
| `payout` | Required complete all-in USD payout, 0–1,000,000; include compensation once |
| `loaded_miles` | Required, >0 and ≤100,000 |
| `deadhead_miles` | Required, 0–100,000; all additional committed miles, including repositioning |
| `diesel_per_gallon`, `mpg` | Optional/null, >0 and ≤100 |
| `tolls`, `driver_cost`, `equipment_trip_cost`, `insurance_trip_allocation` | Optional/null USD trip allocations, 0–100,000 |
| `maintenance_per_mile` | Optional/null USD/mile, 0–100 |
| `operating_hours` | Optional/null, >0 and ≤1,000 |
| `schedule_feasible` | Optional/null boolean; caller-supplied feasibility |

Decimal inputs may be JSON numbers or decimal strings; decimal strings are
recommended. `benchmark.target_all_mile_rpm` is required, null or >0 and ≤100,
with at most two decimal places. It is a revenue target, not cost or profit.
The full schema is authoritative for field shape and bounds.

Equipment enum: `box_truck_26ft`, `cargo_sprinter_van`,
`tractor_carrier_owned_trailer`, `power_only_amazon_provided_trailer`.
Only the synthetic 26-foot box-truck profile (`synthetic-box-001`) supports a
complete recommendation. Other equipment returns a matching-profile question.
Power Only means a tractor pulling an Amazon-provided trailer.

## Outputs and financial meaning

Success is HTTP 200 with `schema_version: "1.0"`, `status: "evaluated"`,
`evaluation`, `next_questions`, echoed `source`,
`confirmation_basis: "caller_assertion"`, `delivery: "canonical_api"`,
`model_invoked: false`, `native_connector: false`.
These last flags describe this deterministic API, not an external model caller.

`evaluation` includes synthetic/profile identity, decision, total miles,
loaded/all-mile RPM, benchmark source and target, target revenue/gap,
estimated costs and operating surplus, missing facts and assumptions.
Amounts/RPM are decimal strings; unavailable figures are null.
`next_questions` contains `{field, question}` objects for missing facts.

All-mile RPM uses loaded plus additional miles. Costs include fuel, tolls,
driver, maintenance, equipment and allocated insurance; missing cost inputs
keep total costs/surplus unknown. Estimated operating surplus is not guaranteed
profit. Equipment costs must include rental mileage charges once if applicable.

Decision precedence: missing facts/profile/target → NEED_MORE_INFORMATION;
otherwise infeasible schedule → DECLINE; otherwise payout below revenue target
or not greater than estimated costs → NEGOTIATE; otherwise ACCEPT.
ACCEPT is an economic/supplied-schedule check, not booking, verified HOS,
route clearance or a guarantee. `evaluated` never means freight was booked.

## Synthetic example

```json
{
  "opportunity": {
    "equipment": "box_truck_26ft",
    "payout": "420", "loaded_miles": "180", "deadhead_miles": "60",
    "diesel_per_gallon": "4", "mpg": "10", "tolls": "20",
    "driver_cost": "80", "maintenance_per_mile": "0.10",
    "equipment_trip_cost": "50", "insurance_trip_allocation": "20",
    "operating_hours": "6", "schedule_feasible": true
  },
  "benchmark": {"target_all_mile_rpm": "2.00", "confirmed": true},
  "facts_confirmed": true,
  "source": "manual"
}
```

| Change only target | Decision | Gap | Costs | Operating surplus |
|---|---|---|---|---|
| `"2.00"` | NEGOTIATE | `"60.00"` | `"290.00"` | `"130.00"` |
| `"1.75"` | ACCEPT | `"0.00"` | `"290.00"` | `"130.00"` |
| `null` | NEED_MORE_INFORMATION | `null` | `"290.00"` | `"130.00"` |

All cases: 240 miles, loaded RPM `"2.33"`, all-mile RPM `"1.75"`.
Remove a cost field to test unknowns; supply `schedule_feasible: false` with
all other inputs complete for DECLINE. Never test with real carrier data.

## Errors, limits and recovery

| Status | Fixed detail / meaning |
|---|---|
| 401 | Unauthorized; `WWW-Authenticate: Bearer` |
| 403 | Forbidden (Host) or Origin not allowed |
| 404 / 405 | Not Found / Method Not Allowed |
| 408 | Request timeout (application body-read deadline) |
| 413 | Request body too large |
| 422 | Invalid request; no submitted values returned |
| 429 | Rate limit exceeded or Too many concurrent evaluations |
| 500 | Internal error |

All application responses have `Cache-Control: no-store`. Proxy errors may
have different formats. Do not treat a redirect, HTML, timeout, invalid JSON
or incomplete response as success. No automatic retry or local/model-arithmetic
fallback. Preserve facts, explain the failure, resolve it, and obtain a new
user-requested attempt. No freight transaction needs reconciliation because
this tool performs none.

Limits: 32 KiB actual request body; 10-second body-read deadline; two concurrent
evaluations and 30 authenticated attempts per 60 seconds globally per process.
Invalid/oversized authenticated attempts consume rate quota. One deployed worker;
state resets on restart. Health does not consume quota. No per-user fairness or
distributed rate limiting is claimed. No Origin header is accepted on evaluation.
The exact configured hostname is required. No regional entitlement system or
subscription plan exists; access is restricted to authorized synthetic review.

## Data handling and availability

This API accepts structured facts only, no screenshot bytes or applicant records.
It makes no model calls and has no application file/database persistence.
Hosting/proxy/runtime logs and retention are not fully verified; no zero-retention
claim. The separate local screenshot workflow sends normalized image pixels to
Meta. The product website beta records/backups follow the public privacy policy;
those practices must not be confused with this synthetic API.

H10 records owner public smoke tests, not native Muse QA or production readiness.
Reboot/recovery, reviewer provisioning, representative load and several public
abuse/proxy checks remain unverified. No availability guarantee. Hackathon
demonstration and native connector approval are separate milestones.
