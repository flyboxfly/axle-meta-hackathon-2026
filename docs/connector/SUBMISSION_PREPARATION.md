# Muse Technical specs — submission status and historical preparation

## Status update — November 8, 2026

Owner-observed portal status: business verification Approved; submitted data
processing questionnaire In review; Technical details Action needed. Technical
specs is checked complete; remaining flow is Credentials → Test. No need to
repeat the other sections. Overall Submitted does not establish testing or approval.

Owner-observed Credentials fields select API key and Authorization header (Bearer).
Proposed label: `Axle synthetic reviewer API`. The portal says it sends a harmless
GET to the required test path. Authentication on that probe is our recommendation,
not an explicit requirement in that help text. This branch adds
`/api/v1/axle/verify`; it is not deployed by this documentation change.

The source expects exactly `Authorization: Bearer <credential>`. Enter only the
raw Axle service credential in the portal API key field when Bearer mode adds the
prefix; never enter a Meta model key or Telegram token. The observed label alone
does not prove prefix behavior: verify a valid-key pass and missing/wrong-key denial
after approved deployment before declaring compatibility. Never expose keys in chat,
screenshots, command output or git. Dedicated reviewer credential provisioning is
still unverified and requires separate approval; do not reuse an owner/shared token.
No portal field, credential, runtime or deployment was changed during implementation.

## Historical status — October 31, 2026

Owner handoff reports the initial application **Submitted**, business verification
**Approved**, data processing questionnaire **In review**, and Technical details
**Action needed** (2 of 3 requirements complete). Submission ID:
`4e022960-47d3-4d0f-9bd4-e384ab6955e8`.

The Credentials screen now shows API key / OAuth / Unauthenticated options.
API key is selected with label “Axle synthetic reviewer access”; the key is empty.
No reviewer token has been provisioned. The screen does not establish storage
protections, model exclusion, Authorization-header handling or Bearer prefixing.
Dedicated reviewer access remains deferred to prioritize the November 4 demo.
Do not use the owner's shared token. Native Muse execution remains unverified.

Initial submission and terms acceptance were owner-authorized and completed;
they must not be repeated as prerequisites. The October 30 preparation below is
historical and predates this submission. This update records the owner's handoff,
not a new portal inspection or acceptance of questionnaire disclosures by Meta.

## Historical H11 preparation — October 30, 2026

The owner's October 30 Technical specs screenshot shows Raw API / Existing MCP,
API URL, optional OpenAPI URL, API/MCP documentation URL, and Access requirements.
Raw API is selected in that screenshot. No credential field or pre-approval
test control is visible. Review is the next step; it has not been inspected here.
Do not submit or accept legal terms as part of this preparation.

## Entries

| Portal field | Prepared value |
|---|---|
| Connection type | Raw API |
| API URL | `https://axle-api-demo.flyboxfly.com` (base URL; evaluation operation is POST `/api/v1/axle/evaluate`) |
| OpenAPI specification (optional) | Use the verified raw URL for `docs/connector/openapi.json` only after the feature branch is published and that exact URL is checked. Otherwise leave blank. Do not enter the disabled runtime `/openapi.json`. |
| API or MCP documentation | Use the verified public GitHub URL for `docs/connector/README.md` after publication. Do not invent a product `/docs` route. |

API URL is proposed as a base URL following the screenshot's placeholder.
Whether Muse expects a base or full operation URL remains to be confirmed.

Access requirements (ready to paste; no secret):

> Restricted synthetic review/demo service operated by Fly Box Fly LLC. Server-to-server HTTPS with a privately provisioned bearer credential; no public signup, subscription plan, OAuth scopes, booking, payments or real carrier records. Only a synthetic 26-foot box-truck profile supports a complete recommendation. Obtain carrier confirmation of supplied facts and revenue target choice, including an explicitly unknown target, before evaluation. Requests must omit Origin. Limits: 32 KiB body, 10-second application body-read deadline, 2 concurrent evaluations and 30 authenticated attempts per minute globally per process. No automatic retry. Bearer-header compatibility, secure reviewer credential delivery and pre-approval testing in Muse remain unverified. Native connector access is not yet available. Contact contact@flyboxfly.com for coordination; do not send credentials by ordinary email.

## Overview assets — owner handoff, public deployment reported complete

- Connector/product name: Axle; operator Fly Box Fly LLC.
- Product: https://axle.flyboxfly.com
- Privacy: https://axle.flyboxfly.com/privacy
- Terms: https://axle.flyboxfly.com/terms
- Icon: https://axle.flyboxfly.com/axle-icon-512.png
- Support/privacy contact: contact@flyboxfly.com
- Policies effective October 30, 2026. Do not equate website beta retention with
  the separate synthetic evaluation service.

## Compatibility and credential gates

1. Confirm the portal's interpretation of API URL and acceptance of the static
   OpenAPI document. The raw API choice alone does not establish compatibility.
2. Inspect Review and any official secure credential instructions without final
   submission or legal acceptance. Determine whether credentials are protected
   configuration, excluded from model-visible tool arguments, and sent in the
   Authorization header. No secure handoff mechanism is verified yet.
3. Resolve dedicated reviewer access. Current runtime accepts one shared token;
   no independently revocable reviewer account/token exists. Do not disclose
   the owner token or claim a reviewer account has been provisioned. Any token
   replacement, new authentication feature or runtime change needs separate
   owner authorization.
4. Confirm whether pre-approval testing is available and whether Muse can obtain
   the carrier review required before asserting confirmation. There is no
   native confirmation UI integration in this repository.
5. Verify a real Muse-selected call, canonical result handling, unknown facts,
   denied access, and failures through the supported flow before claiming
   native Muse integration. Approval and discovery remain separate.

## Hackathon positioning

Fly Box Fly LLC is participating in the Meta AI Developer Hackathon, Startup
Track, with a November 4, 2026 submission deadline. The local Meta API workflow
and deployed economics API demonstrate the intended specialized delegation.
Muse consumer-agent/mobile integration is a separate proposal, outside the
hackathon scope per owner clarification. No approval, endorsement or partnership
is claimed. If a Muse-style experience is simulated, label it a simulation;
real model/API execution must be identified separately from native integration.

## Sources and limits

- Owner Technical specs screenshot supplied in the H11 handoff, October 30.
- https://platform.muse.ai/docs rechecked October 30: sections 3, 5.4–5.5 and 6.
  Guidelines request API/MCP documentation, secure credential instructions and
  dedicated test access; they do not specify the observed form's secret flow.
- No final submission, portal mutation, agreement acceptance, reviewer credential
  issuance or native Muse call was performed in this work.
