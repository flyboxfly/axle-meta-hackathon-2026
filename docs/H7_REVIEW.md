# H7 slice 1 — axleAPI local external-client contract

Base: merged H6 main a0bbbb035eb292bbadd4c237d28bc5c7d7dad693.
Branch: feature/h7-axle-api in an isolated worktree.
Status: local review candidate; no publication or deployment.

## Change

POST /api/v1/axle/evaluate accepts an explicit opportunity, benchmark envelope,
facts_confirmed boolean, and manual/screenshot source. Benchmark is required;
its target is a positive decimal up to 100 with at most two decimal places, or
explicit null for unknown. Both confirmations require actual JSON true, not
strings or numbers. Extra fields are rejected at every request-object boundary.
No carrier identity or production profile selection is accepted.

The existing deterministic evaluator supplies Evaluation. Response adds schema
version, source, caller-assertion confirmation basis, canonical_api delivery,
model_invoked=false, native_connector=false and field-linked next questions.
The endpoint completes a calculation even when its decision is NEED_MORE_INFORMATION;
status=evaluated means calculation finished, not load accepted or booked.
No inference SDK call, screenshot extraction, data storage or booking occurs.
Screenshot source indicates caller-reported provenance, not inspected pixels.
Caller confirmation is not proof of human review. A connector implementation must
obtain real carrier review before asserting it; never let a model invent consent.

Bearer authorization uses existing AXLE_DEMO_TOKEN. Host/client and same-origin
checks keep this a local preview. JSON result responses use Cache-Control: no-store.
The localhost testserver host is also accepted with a loopback/test client only.
This is not a remote deployment boundary. Existing bearer route, browser route,
model schemas, paid budgets and CLI follow-up loop remain unchanged.

## Validation

107 offline tests passed in 1.73s (93 existing plus 14 H7 cases); git diff --check
passed before documentation. New coverage exercises HTTP request/response behavior
using an in-process TestClient, with MODEL_API_KEY absent: target sequence, null
costs, structured questions, unsupported equipment, strict confirmation, missing
fields, extra identity rejection, invalid target precision, auth, local/Origin
checks, OpenAPI operation ID and unchanged legacy default.

This is offline HTTP-handler evidence, not separate-process TCP, model-selected
external delegation, owner Mac validation, native Muse access or deployed service.
No new paid request, GitHub mutation, production access or deployment occurred.

## Remaining H7 work

- Review this contract and publish branch/draft PR only after owner approval.
- Validate a separate loopback client, then a model-selected external API call.
- Resolve exact Muse intake transport/authentication expectations from current
  official documentation/portal; no invented MCP/A2A compatibility claim.
- Build/review remote authentication, HTTPS/proxy trust, quotas, body/error limits,
  credential scope and reviewer access before exposing anything.
- Current FastAPI validation errors may include supplied values; review/redact
  that behavior before handling private data remotely. OpenAPI currently documents
  the authorization header rather than an OAuth account-connection workflow.
- Prepare reviewer examples, data handling/support documentation and synthetic
  test access. Native connector approval is still pending.
- Introduce Muse Code after verifying Intel Mac support and authentication.

Startup Track and VPS reuse are permitted per owner clarification. Retain required
opening disclosure of pre-existing concept/brand/VPS versus new hackathon code.
