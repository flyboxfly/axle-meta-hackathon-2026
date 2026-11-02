# H15 bounded owner-run live-test plan

Prepared November 2, 2026. Planning evidence only. No installation, listener,
tunnel, bot registration, secret provisioning or live call performed. This plan
is not authorization to run; every section marked DECISION needs the owner's
explicit approval against a concrete reviewed commit. Do not merge, deploy,
change private configuration, reset databases, or spend outside existing
credits. The earlier one-evaluation approval was consumed; this plan requests a
new, separately bounded approval.

## Scope

One attended owner-only run of the real opening-price workflow on branch
`feature/h15-opening-bid-foundation` (draft PR #15): the owner sends one real
opportunity screenshot in a private chat with a dedicated bot; Muse Wonder
(`muse-wonder-1.0`) extracts an UNCONFIRMED draft; the owner reviews, corrects
and confirms an exact revision; Wonder selects the revision-only pricing tool;
deterministic Decimal code returns an internal preliminary opening price
labeled DRAFT — NOT SENT. No broker outreach, marketplace bid, booking or
autonomous commitment. No invited carriers. No StarNet changes.

Out of scope: itemized cost normalization, saved-profile reuse for pricing,
second screenshots beyond the spare budget, and any public evidence.

## Bounded model attempts

Lifetime caps enforced by the launcher and the durable attempt ledger:
global 4, per-carrier 4. Planned use is 2 attempts: 1 screenshot extraction +
1 pricing selection. The remaining 2 are spare for one failed extraction
followed by one re-sent screenshot, or one failed selection followed by one
re-confirmation and re-price. There are no automatic retries; every failure is
terminal for that attempt and keeps its reservation. If all 4 attempts are
consumed or any outcome is uncertain, the test ends and enters recovery below.
A timeout never authorizes a retry.

## Credit and data-use checks (before approval)

1. DECISION: confirm the provider account, Wonder entitlement, and an accepted
   account spending ceiling. Four attempts cap request count, not dollars,
   output-token charges or account-wide use. No dollar guarantee is available.
2. Confirm Standard mode (content not used for training) or record the owner's
   explicit Contributor-mode acceptance. See the pricing notice in the
   verification record below.
3. Confirm acceptance of the Telegram/tunnel intermediaries and their
   applicable terms: the screenshot travels owner -> Telegram -> loopback
   pilot -> Meta, plus a temporary Cloudflare tunnel for ingress. The tunnel
   URL is public; webhook secret plus exact numeric private-chat allowlist
   remain required.
4. Record the reviewed commit pin, the offline suite result on that pin, and
   the `pip check` plus reviewer OpenAPI export results.

## Official contract verification (November 2, 2026)

- Telegram Bot API `getFile`: bots download files up to 20 MB; `getFile`
  takes `file_id` and returns a `File` object; download via
  `https://api.telegram.org/file/bot<token>/<file_path>`, valid at least
  1 hour. Source: https://core.telegram.org/bots/api#getfile
- Meta models: `muse-wonder-1.0` on Model API; Wonder and Spark take the same
  requests on the same endpoints (a model ID change); Wonder supports image
  understanding, tool calling and structured output. Wonder Full is not on
  Model API and is not claimed. Source: https://dev.meta.ai/docs/models
- Responses image input: `input_image` blocks with a plain-string `image_url`
  (base64 data URL supported) inside a user message. Structured output:
  `text.format` JSON Schema with strict subset. Tool calling: `tools` entries
  of type `function`; `function_call` output items with name, arguments,
  `call_id`, `status`; results via `function_call_output`. Model arguments
  are not guaranteed to validate; this runtime validates before use.
  Sources: https://dev.meta.ai/docs/image-understanding,
  https://dev.meta.ai/docs/structured-output,
  https://dev.meta.ai/docs/tool-calling
- REST response shape: visible text comes from `output[]` message
  `output_text` parts; top-level `output_text` is an SDK-only helper and
  must not be read over direct HTTP. Reasoning effort `low` is valid;
  reasoning tokens share `max_output_tokens` with visible output. The
  extraction cap stays at the original 4096 pending evidence that it is
  insufficient. Sources:
  https://dev.meta.ai/docs/api-reference/responses/schemas,
  https://dev.meta.ai/docs/reasoning
- Account-specific Wonder access, latency and billing behavior remain
  untested; the first approved extraction tests them. If an extraction
  fails, dashboard output tokens near the 4096 cap only suggest
  truncation; daily totals alone do not prove it. Likewise, a small
  reported file size makes media failure less likely but does not rule
  out download, format, or dimension faults.

## Staged procedure after explicit authorization

Follow the H13 isolated owner-test arrangement (separate Mac checkout at the
reviewed pin, fresh venv, pinned installs, offline suite first, private
0700 directory outside sync/backup, dedicated bot, numeric enrollment,
30-minute attended admission window while safely parked, temporary tunnel to
127.0.0.1:8013, loopback/tunnel 403 probes, `setWebhook` through the private
helper). Differences for this opening test:

1. Operator helper action is `prepare-opening` (confirmation phrase PREPARE
   NEW OPENING TEST), writing `approved_real_opening_test`. The synthetic
   approval key is rejected by this launcher and vice versa.
2. Launch with `python -m axle_hackathon.opening_launch` and only
   `AXLE_PILOT_CONFIG_FILE` set. No other overrides.
3. Owner sends /start, chooses session, then sends ONE screenshot (photo or
   PNG/JPEG document). Expected: UNCONFIRMED draft reply with
   screenshot-derived facts kept separate from carrier pricing, plus cargo,
   handling and schedule questions.
4. Owner corrects figures with `field value` messages as needed
   (payout, loaded, deadhead, weight, target, cpm, minimum, reposition,
   counter). Each applied correction creates a new revision and invalidates
   prior confirmations. An `itemized` CPM answer is rejected with a
   normalization notice and leaves pricing unavailable.
5. Owner reviews and confirms the exact current revision with /confirm, then
   sends /price once. Expected: internal preliminary opening price with
   checkable economics, labeled DRAFT — NOT SENT. Unknown schedule allows
   preliminary pricing but never becomes acceptance.
6. Owner sends /refresh once, then /forget. Observe the acknowledgement.
   Any missing result, duplicate-looking result, malformed response, stalled
   privacy command or provider rejection ends the test: stop commands and
   enter recovery. Do not spend spare attempts to debug.

## Recovery decisions

| Event | Required action | Resumption rule |
| --- | --- | --- |
| Startup/probe/Host failure before registration | Close tunnel; inspect fixed error and file modes | Correct setup only after clean exit |
| Extraction/price timeout, provider error or unknown send | Close webhook/tunnel; graceful stop; retain owner while draining | No repeat of that attempt; spare budget needs fresh explicit approval |
| /forget missing/stalled | Stop admission; drain; inspect original closed DB | Deletion resolved before any new consent/test |
| Unsupported update/retry backlog | Remove webhook/drop pending on dedicated bot; close tunnel | Do not reset IDs/state to accept it |
| Tunnel disconnect or hostname change | End admission; stop and drain | New URL needs reviewed config + registration after clean stop |
| Drain incomplete after two minutes | Keep process and files; record failed test | No automatic restart or forced kill |
| Crash/forced stop | Close route/webhook; quarantine state; outcomes uncertain | No relaunch under this plan |
| Accidental secret exposure | Close route, drain, revoke as authorized | No further model calls |

## Retention and closeout

No pilot DB backup is planned. Preserve intact state during incidents. After
clean drain, completed /forget and aggregate inspection (attempt totals only,
no raw messages/IDs/screenshots), retire webhook/tunnel and remove private
config/state within 24 hours, keeping only nonidentifying pass/fail/count
evidence. Removal does not erase Telegram, tunnel, provider, OS or
storage-media histories. Reuse later requires a new decision and preserves
the historical attempt ledger.

## Evidence record

Runtime pin, Python/tunnel versions, admission window, attempt count and
ledger totals, expected vs actual canonical figures, refresh/forget outcomes,
exit status, aggregate queue/privacy counts, pass/fail, and whether evidence
was owner-operated live or offline. Omit tokens, token URLs, chat/user IDs,
raw messages, provider response IDs, screenshots and figures that identify
the owner's operating costs from git. One live success demonstrates only the
tested case, not general accuracy or reliability.
