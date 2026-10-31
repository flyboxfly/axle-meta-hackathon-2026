# H13 injected HTTP adapters

October 31, 2026. Baseline 7f18b6c. Fake HTTP transports and invented records only.

MetaResponsesClient implements the narrow responses.create interface consumed by
PilotDelegator using direct HTTP POST to the existing Meta base /v1 plus /responses
path (confirmed against installed SDK resource source). No SDK layer/retries is used.
Actual live Meta compatibility remains unverified. TelegramSender uses sendMessage
at the fixed Telegram HTTPS host, an explicit token and server-approved numeric chats.
Only plain text and chat_id are sent. Success requires ok true and a positive message
ID for the requested private chat. It does not register a webhook or enroll users.

Both adapters stream responses, reject redirects/non-200/compression/duplicate JSON
keys, cap response bytes (64 KiB provider, 32 KiB Telegram) and expose fixed errors
without remote payloads, exception text or token URLs. Provider requests are capped
at 32 KiB; sender text at 4,000 characters. Injected clients must use reviewed no-retry,
phase-timeout settings: arbitrary clients/transports can bypass that configuration.
Total elapsed checks run before accepting chunks and parsing. A stalled read still
requires HTTP read timeout; these checks cannot interrupt socket I/O. Existing caller
wait bounds retain capacity/ownership until actual exit. No hard total cancellation
claim is made. HTTP logging outside these adapters could expose secret URLs and must
be disabled/sanitized in final host configuration.

PilotLifecycle optionally takes ownership of explicit transport_clients. Once all
execution/request drain fields are true, it closes clients before releasing storage.
Successful closes are removed to avoid repeating them on later inspection. Cleanup
failure retains storage and raises a fixed error; later inspection may retry the
remaining client. Construction failure attempts client cleanup and always closes
its newly created inbox. No live factory or credential loader wires this composition.

Five new cases verify the whole worker-to-HTTP-provider-to-HTTP-sender flow, single
attempt sanitized failures for oversize/duplicate JSON/read timeout/redirect, and
unapproved chat rejection. Existing provider/sender timeout lifecycle tests now also
verify client close occurs once and only after late operations exit. Full suite:
345 tests pass. Dependency/OpenAPI/diff checks pass. No paid calls, credentials,
real carrier data, live sends, merge, deployment or infrastructure changes.

Sources inspected October 31, 2026: https://core.telegram.org/bots/api#sendmessage
and https://www.python-httpx.org/quickstart/#streaming-responses .

Next: integrated adapter/error/cleanup review, fixed production factory with explicit
transport configuration, logging policy and actual deadline strategy. Retained-owner
process policy, inbound admission/SQLite latency, provider data terms, enrollment/order
recovery and backup deletion recovery remain live-use gates. Keep synthetic-only
processing enforced by PilotDelegator; no real-carrier clearance follows.
