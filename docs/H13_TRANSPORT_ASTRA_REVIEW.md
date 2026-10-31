# H13 adapter and cleanup review

October 31, 2026. Baseline draft 16b4634. Assistant source review and offline fault
injection with invented acknowledgements; not an independent audit or live evidence.

## Reproduced and fixed

Medium: Telegram acknowledgement validation used Python equality for chat IDs,
accepting true and 1.0 as chat 1. Null/list chat objects instead raised AttributeError
outside the fixed-error path. Validation now requires a chat object, an exact integer
ID equal to the bound destination, and private type before acknowledging success.
Four cases failed on baseline and now reject with the fixed uncertain-delivery error.
These malformed responses never change the outbound destination; the gap concerned
trust in reported delivery, not a demonstrated cross-carrier send.

Medium: failed-construction cleanup stopped at the first client.close exception and
surfaced its raw text, skipping later clients. It now attempts each listed client,
always releases the newly created inbox, and reports fixed cleanup-incomplete text
if any close failed. A fifth baseline regression reproduced both the skipped client
and exposed error. Actual failed client closure remains failed; attempting cleanup
does not guarantee that resource was reclaimed.

An additional test verifies normal shutdown cleanup failure keeps the database owned,
uses a fixed error, retries the remaining close on later inspection, then releases
storage without repeating already successful cleanup.

## Boundaries and outstanding integration work

Response limits cap accepted accumulated bytes. A transport may already allocate a
larger chunk before the adapter sees it. Fake transports do not establish socket or
memory-pressure limits. Elapsed checks occur between reads; a stalled read cannot
be interrupted by these checks. Caller timeout still retains executor capacity and
ownership until actual exit. No hard total network cancellation claim is justified.

The endpoints are fixed and model-controlled identities/targets remain excluded from
provider inputs. Direct HTTP has no SDK retry layer; arbitrary injected transports
could still retry or log tokens. A final factory must construct the reviewed clients,
prevent alternate endpoint/configuration overrides, disable sensitive HTTP logs and
make ownership transfer explicit. Inbox construction currently precedes lifecycle
cleanup handling; if opening the database itself fails, supplied clients remain the
caller's cleanup responsibility. The factory must cover this path.

Client.close remains synchronous and can exceed the scheduler join timeout. Keep
shutdown off-loop; retain the owner on failure and document host termination policy.
Construction cleanup assumes factories launch no background work. Exception text is
sanitized at reviewed boundaries, but traceback-local capture and external HTTP logs
can still expose credentials/private payloads and must be excluded in hosting.

Validation: **351 tests passed**. Dependency, reviewer OpenAPI and whitespace checks
passed. No paid calls, credentials, real records, live sends, merge, deployment or
infrastructure changes.

Next: fixed synthetic-only composition factory and complete offline host-to-HTTP
rehearsal, with explicit client ownership on all constructor failures. Prepare an
isolated owner-test plan naming remaining network deadline, host admission/SQLite
latency, provider data-use, enrollment/order and backup recovery gates. No live-use
approval follows from this review.
