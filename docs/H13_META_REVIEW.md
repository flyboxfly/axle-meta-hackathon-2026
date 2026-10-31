# H13 synthetic Meta adapter candidate

October 31, 2026; based on draft head 446e3dc. `pilot_meta.PilotDelegator`
adds one injected Responses-compatible selection request for a synthetic hypothetical
confirmed opportunity, followed by deterministic calculation through PilotMemory.
There is no launcher, credential read, public endpoint or live provider verification.
Existing synthetic browser/reviewer flows are unchanged.

## Implemented

Authorization, current consent, exact integer revision, confirmation and synthetic
hypothetical provenance are checked before provider invocation. The request sends
only opportunity facts and revision; profiles, software, targets, identities and
consent tokens stay server-side. Source/scope text is untrusted input. The versioned
coordinator prompt permits one deterministic planning tool; its only argument is
revision. No model output changes carrier facts or acceptance authority.

Completed response and exactly one completed known tool call are required. Extra
arguments, duplicate JSON keys, non-integer revisions and malformed/incomplete output
fail closed. Input and tool-argument sizes are bounded. Provider exceptions become a
fixed message without SDK payloads. The adapter makes one request, with no retry loop.
The future host must configure SDK retries off and bound timeout; an injected client
can otherwise retry internally. One instance rejects concurrent selections.

After the response, memory.evaluate rechecks the original token, expiry, confirmation
and revision under the facade lock and computes canonical results from current facts.
An intervening edit, expiry, forget or renewed consent rejects the old completion.
The return is current at calculation time; a future transport must recheck before
actual send. This module neither schedules tasks nor delivers messages.

The model does not receive the result. Output trace labels the deterministic
opportunity-analyst tool actually executed; it does not claim five model agents,
specialist model inference or a full conversational round trip. Instruction version
pilot-selection-v1 is implemented inline; the broader Markdown roles remain proposed.
Screenshot extraction, progressive conversational intake and negotiation are future work.

## Validation and release limits

Assistant Linux: full pytest **261 passed in 2.59s** (243 prior + 18 adapter cases).
Mocked provider tests cover minimal input scope, canonical output, altered/extra/
duplicate arguments, invalid completions, authorization before invocation, real-offer
rejection, changed state during response, and sanitized provider failure without retry.
No paid call or real carrier data. OpenAPI, dependency and diff checks accompany this slice.

This adapter is a synthetic development component, not a live pilot release. Provenance
labels cannot establish that arbitrary free text contains no private data; use invented
fixtures only. Global/per-carrier paid budgets, durable deduplication, private-data
provider review and transport limits remain required before a live launcher is added.
The [Astra review](H13_ASTRA_REVIEW.md) holds still apply, including durable privacy
recovery and one storage owner. Next: durable Telegram inbound/task processing and
privacy-command recovery, then isolated hosting preparation and integrated review.
