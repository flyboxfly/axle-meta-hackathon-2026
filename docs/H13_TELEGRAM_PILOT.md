# H13 — carrier pilot specification

Status: design baseline only. Prepared October 31, 2026.
Base inspected: main 8358f191f0251995687ba7dda21ede4a88c9af15; no open PRs.
Repository recursive tree has no existing AGENTS.md.
No runtime, deployment, new credentials, paid model call or real-data processing is added here.

## Goal
Carrier sends an authorized real opportunity in Telegram; Meta extracts draft facts;
carrier clarifies/confirms; Meta selects a scoped freight tool; deterministic economics,
schedule review and optional negotiation draft return through Axle. Revised terms trigger
fresh review. Demonstrate one complete carrier workflow, then a second isolated carrier.

Use the existing Python application stack with a separate pilot entry point and storage.
One application contains coordinator and scoped role modules. Do not add a framework merely
to label functions agents. Record actual model delegation separately from deterministic functions.
Runtime definitions: [roles](agents/README.md).
Developer guidance: [AGENTS.md](../AGENTS.md).

## Deliverable sequence
1. This design baseline: guidance, versionable roles, acceptance criteria.
2. Pure pilot core: carrier/profile/opportunity schemas, consent and revision state,
   deterministic cost adapters and confirmation invalidation; offline tests.
3. Meta adapter: real-data extraction instructions, structured updates, scoped role/tool selection,
   exact fact preservation and canonical output. No synthetic-path prompt reuse by relabeling.
4. Telegram adapter: private allowlist, screenshot/text/buttons where tested,
   durable update processing, private secret launcher and offline transport tests.
5. Isolated hosting plan and reviewed deployment; webhook registration after approval.
6. Owner smoke test, then invited carrier tests; permission for any public evidence.
7. Approved brand reuse, judge README/demo evidence and final submission preparation.

## Carrier state and consent
Server maps numeric Telegram user ID AND private-chat ID to an approved carrier ID.
Display names/MC/DOT do not authenticate. No public self-enrollment or group chats in first slice.
Owner approves tester mappings out of band. Never infer shared-company access.
Every state read/write/tool invocation is scoped to that binding. Model cannot choose tenant.
Separate per-carrier profiles and opportunities; no shared conversation history.
Fields carry value/unit/source/status/effective time/confirmed time/revision.
Statuses include extracted, supplied, confirmed, unknown and superseded.
Stable equipment, changing costs and expiring position/availability have different freshness.
Record persistent-profile consent and processing disclosure before durable profile use.
Provide session-only option with disclosed volatile-session expiry; no durable profile if declined.
Telegram/provider histories and infrastructure logs remain separate; promise no zero retention.
Document actual retention/deletion and provider data-use terms before inviting testers.
No private data in git or public traces. Secondary research/integration discovery use is separate
from serving the carrier. No automatic model training/RL or data sale.

Software fields distinguish subscribed, planned and interested. Capture repeated task and desired
outcome optionally, after useful assistance; no mandatory survey before evaluating an opportunity.
Success priorities are carrier statements with explicit tradeoffs, not hidden model preferences.

## Opportunity and confirmation state
RECEIVED -> DRAFT -> CLARIFY -> REVIEW -> CONFIRMED -> EVALUATING -> RESULT.
A revision creates a new immutable snapshot and returns affected facts to REVIEW.
Confirmation references exact profile, opportunity, target and schedule revisions.
Reject stale button actions and results; serialize work per carrier.
Update payout/mileage/stops/handling/appointments -> invalidate result and affected checks.
Profile cost/target/availability changes invalidate dependent results.
Unknown target, costs or schedule can produce partial observations, not complete ACCEPT.
No automatic booking; economic ACCEPT is a recommendation under supplied assumptions.
Distinguish real offer, hypothetical operation, model draft and carrier assertion.

## Economics contract
Preserve existing synthetic API and its schema/profile/defaults/deployment pin.
New pilot results have explicit opportunity origin, scenario kind, profile ID/revision,
confirmed inputs, calculation version and execution source. A flag toggle is insufficient.
Reuse pure Decimal arithmetic only with explicit real-data provenance and no synthetic defaults.
Initially support validated equipment/cost configurations; unsupported configurations fail clearly.

All operating miles are explicit nonoverlapping segments. Missing mileage is not zero.
Cost modes: itemized OR carrier-supplied all-in planning CPM with confirmed included items.
Rental = allocated base + rate * chargeable miles, applying known included-mile/overage terms;
do not assume every agreement bills identically. Covered maintenance is not added twice.
Finance/ownership allocations, insurance (including applicable trailer interchange), fuel,
driver labor, tolls, uncovered maintenance and miscellaneous costs follow confirmed bases.
Unknown coverage/allocations remain unresolved. Separate contingencies from incurred costs.
A reserve-adjusted planning figure is not accounting profit. Do not invent service fees.
Trip-specific costs are added to CPM only if explicitly excluded from it.
Target, opening and reservation point remain distinct. Model cannot override confirmed values.

## Model and tool execution
Keep Meta model use meaningful: extraction, next-task selection and supported interpretation.
Existing model is muse-spark-1.3; verify live compatibility before claiming pilot support.
Canonical economics comes from code, not model arithmetic.
Do not add a mandatory second model round trip merely for conversational polish.
Use structured templates for canonical results; any model narrative cannot replace verified figures.
Bound request size, completion time, per-carrier/global paid budgets and concurrency.
Never blindly retry paid calls; failures retain inputs and show no new verified decision.
Role traces include role, tool, status, revision and timing; no hidden reasoning or raw private payload.
Do not claim native Muse integration or development tools as runtime delegation.

## Telegram and hosting proposal
Dedicated bot; public HTTPS webhook on a separate pilot service, not the synthetic API/browser app.
Candidate host name to be selected and checked, not claimed provisioned.
Validate Telegram webhook secret header before state access; private allowlist before model work.
Validate update/media sizes/types; normalize images and strip metadata.
Accept permitted updates into a durable scoped queue with unique update ID before acknowledging.
Worker records processing state and bounded outbound delivery. Duplicate updates cannot repeat inference.
Crashes/outbound ambiguity must not trigger blind paid retries; surface recovery state.
Specify dedup retention, queue limits, session/profile retention, deletion and backup behavior
in the deployment design before go-live. Do not log bot-token URLs or raw SDK errors.
Pilot-owned storage/volume and secrets only; no access to production carrier/website database.
Webhook deployment must account for the unresolved shared-proxy hold. If isolation cannot be
achieved without protected changes, present another hosting option; do not silently modify proxy.
No polling while webhook is configured. Do not repurpose StarNet's shared bot without inspection.

## Required acceptance evidence
- Unauthorized user/private chat rejected before storage disclosure or paid work.
- Two carriers cannot access each other's profile, opportunity, task or callback.
- Unknowns remain null; corrections supersede prior facts with traceable revision.
- Rental maintenance inclusion, rental mileage, trailer-insurance inclusion and CPM exclusions
  have meaningful calculation cases; no duplicate costs or silent defaults.
- Changed terms/costs/availability and stale callbacks invalidate prior confirmations/results.
- In-flight old results cannot overwrite newer revisions.
- Duplicate webhook, crash recovery and model failure cannot duplicate paid evaluation.
- Counteroffer lacks ready-to-send status without confirmed limits; internal floor never leaks.
- Schedule unresolved/conflict cannot become a full acceptance through economics alone.
- Secret/oversized/malformed webhook/media rejected; logs contain no secrets/private payloads.
- Synthetic regression suite and exported reviewer contract unchanged.
- Live Meta extraction/selection and Telegram send/receive independently evidenced.
- First owner workflow before additional testers; carrier feedback recorded with consent.

## Pilot success and judge evidence
Measure case completion, corrections, time spent (and baseline when available), repeat use,
carrier-stated usefulness and whether the recommendation matches the carrier's objective.
Do not claim savings or improved earnings without measured support.
Tester identity, quotes, screenshots and results require permission for public use.
Interested testers/partners are not executed contracts or validated outcomes.
README links to roles, architecture, setup, limitations and actual execution evidence.
Opening disclosure: “Axle’s concept, brand and VPS pre-existed; we built this standalone
application, Meta model integrations and demonstrated workflow for the hackathon.”
Alpha instructions are also pre-existing design inputs; no claim all agent concepts originated here.
