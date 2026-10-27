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

## Owner Mac verification — October 27, 2026

Owner checked out published feature/h7-axle-api (publication head 15a4232) and
reported 107 passed in 2.83s. Initial server process 47645 was stopped to recover
the existing local token privately; no credential value was supplied in chat.
Restarted server process 47730 served a separate Terminal Python/httpx client
over loopback TCP. Owner output confirms all three assertions passed:

| Confirmed target | Decision | Gap | Costs | Estimated operating surplus after allocated costs |
| --- | --- | --- | --- | --- |
| $2.00 | NEGOTIATE | $60 | $290 | $130 |
| $1.75 | ACCEPT | $0 | $290 | $130 |
| Unknown | NEED_MORE_INFORMATION | null | $290 | $130 |

The client also asserted model_invoked=false and delivery=canonical_api and
printed the expected request for a confirmed all-mile revenue target. This is
owner-executed separate-process HTTP evidence, not an assistant-run TCP test or
model-selected delegation. No paid inference was invoked by this verification.
Owner supplied clean shutdown output for process 47730. Server is stopped.

This later record supersedes the pending Mac/separate-client status above.
PR #6 is published as draft; this evidence addition is local pending publication.
Model-selected external API delegation, remote hosting and native Muse access
remain unverified. No merge or deployment authorized.

## Slice 2 candidate — model-selected external delegation harness

New external_agent.py keeps the Opportunity-only tool schema: the model cannot
supply benchmark, confirmation or source. It requires one completed recognized
model-selected call with exact confirmed facts, posts the caller-owned envelope
to /api/v1/axle/evaluate, validates response shape and explicit provenance, then
submits the full canonical envelope as function_call_output linked by call_id and
previous_response_id. A completed nonempty follow-up with no further calls is
required. Two model requests maximum, one HTTP evaluation, no forced choice or
automatic retry. No partial success on timeout or protocol/HTTP failure.

CLI: python -m axle_hackathon.external_agent (only after approved publication,
Mac synchronization, local server start and secure credential setup). It displays
the complete synthetic case and requires CONFIRM before any request. The health
preflight checks server availability only, not token validity. Model timeout is
20 seconds per request, max_retries=0; HTTP timeout is 15 seconds, redirects off,
fixed loopback destination, trust_env=False. No caller-selected destination.

Success output contains canonical result and bounded round-trip metadata, no raw
model prose or reasoning. Nonempty model prose is required but not validated or
displayed; completion does not prove prose accuracy. tool_result_submitted means
the canonical output was sent and the provider returned a completed follow-up;
it is not proof of native Muse consumer-agent integration. Synthetic data only.
Existing H1 CLI and H5 browser completion contracts are untouched.

Failure logs contain fixed stage and elapsed milliseconds only. Failure exceptions
expose fixed stage, never provider error text, token or request bodies. Requests
run as a local CLI; browser paid-operation limiter does not govern this CLI.
Every owner-approved invocation may spend two paid requests. Do not retry blindly
or claim this fixes the previously observed after-tool timeout.

Validation: 121 offline tests passed in 1.77s (107 prior + 14 harness cases).
Fake model responses exercise actual in-process HTTP handlers, call-result
serialization/linkage, invalid selection/facts/injection rejection, HTTP auth
failure, second-request timeout/incomplete/extra-call/empty-text failures, and
log redaction. This is not installed-SDK wire serialization or live model evidence.
No live slice 2 inference, Mac slice 2 run, remote publication or deployment yet.

Official Meta tool-calling and Responses docs rechecked October 27, 2026:
https://dev.meta.ai/docs/tool-calling
https://dev.meta.ai/docs/protocols/responses
Uses the documented function_call_output / previous_response_id follow-up.
No new API parameters or provider introduced.

Publication proposal: append these changes plus owner slice 1 evidence to draft
PR #6 after owner approval. No merge/deployment requested by this candidate.
