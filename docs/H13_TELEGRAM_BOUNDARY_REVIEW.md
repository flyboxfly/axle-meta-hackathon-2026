# H13 Telegram boundary and worker — offline candidate

October 31, 2026. Based on draft head 78e4a18. No bot credential, webhook
registration, live message, deployment, paid inference or real carrier data.

`pilot_telegram.create_app` exposes only POST /telegram/webhook with docs disabled.
An exact host and explicit 32–256-character configured secret are required. The
X-Telegram-Bot-Api-Secret-Token header must occur once and match before body reading.
The streamed body is limited to 8 KiB with a five-second deadline. JSON duplicate
keys are rejected. Only message updates containing exact /evaluate or /forget
commands are supported. Sender must be a non-bot, chat must be private, and numeric
user/chat must match the server binding. No display-name authentication or media fetch.

Telegram protocol was checked against its official API on October 31:
https://core.telegram.org/bots/api#setwebhook and https://core.telegram.org/bots/api#update.
Telegram documents the secret header, retries on non-2xx webhook responses, and
update-ID deduplication. The application's minimum secret length is stricter than
Telegram's. Unsupported update/command responses are currently 400, so Telegram may
retry them; choose a final ignored-update/poison-message policy before registration.

Authenticated supported commands durably submit metadata before 200 acknowledgement.
Duplicates are recognized before requiring active consent, so a prior evaluate can
be acknowledged after forget without reprocessing. Evaluation uses the active
server-held consent and confirmed snapshot. No client/model supplies those values.
Forget requires no ongoing processing consent, records deletion intent and clears
active state. The privacy worker remains inbox.process_forget.

The injected run_evaluation worker claims once, invokes PilotDelegator, recomputes
and compares canonical output under the memory lock immediately at delivery, and
sends plain text to the bound numeric chat. The sender must return True only after
validated Telegram success; any exception or other return means uncertainty. There
is no automatic retry after provider/send ambiguity. The lock is held during delivery
to serialize privacy/state changes; a real sender MUST have a short enforced timeout
and retries disabled. A request already being sent cannot be recalled by later forget.
Worker failure errors are fixed and contain no provider details or token URLs.

This is an offline integration seam. Tests invoke workers explicitly with a mocked
model and fake sender. No scheduler, Bot API client, launcher, public hosting or worker
drain loop is installed. Existing opportunities and consent must be prepared through
the trusted facade; carriers cannot yet perform intake, disclosure acknowledgement,
profile confirmation or edits through Telegram. No screenshots, buttons, software
integration or real-data model mode have been added.

Before live use: finish the carrier intake/consent/review flow, worker scheduling and
recovery, paid budgets/rate limits, HTTP client timeouts, safe server logging, command
ordering, ignored-message policy, outbound delivery review and private-data account
conditions. Body-limit tests alone do not establish network denial-of-service defense.
Host/proxy limits and single-owner storage configuration need the isolated deployment
plan. Backup-restore privacy and integrated Astra review remain release dependencies.

Validation: assistant Linux, unchanged lock reinstalled into a fresh temporary venv
after the earlier environment was cleared. Full pytest **279 passed in 3.35s**
(267 prior + 12 boundary/worker cases). Tests cover authenticated mocked round trip,
duplicate suppression, sender/chat/secret rejection before queue writes, body/host/JSON
limits, withdrawal, stale delivery and ambiguous send failure. No live Telegram test.
