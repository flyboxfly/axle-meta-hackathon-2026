# H13 isolated owner-test deployment and recovery plan

Prepared November 1, 2026 (America/New_York). Planning evidence only. No installation,
listener, tunnel, bot registration, secret provisioning or live call performed.
Runtime pin: ab020afa120bf1656c5ae49f3021ce1456b86a58, reviewed with 363 offline tests.
This document does not authorize launch. [Launcher review](H13_LAUNCH_ASTRA_REVIEW.md)
and [exact invented-input rehearsal](H13_FACTORY_ASTRA_REVIEW.md) provide evidence.

## Proposed arrangement

Use B's Mac for one attended, 30-minute admission window while safely parked, with a
fresh Python 3.11+ venv, a separate source checkout and private local state directory.
A temporary Cloudflare Quick Tunnel forwards HTTPS to 127.0.0.1:8013. No cloud server,
production database, DNS change, shared Coolify proxy, Docker or VPS changes are needed.
This is a proposed choice; the Mac's compatible Python, disk/location and tunnel
binary version have not been inspected. No new paid hosting/subscription is proposed.

Telegram -> temporary HTTPS tunnel -> loopback pilot -> dedicated local SQLite.
The pilot separately sends scoped invented figures to Meta and replies through the
Telegram Bot API. Cloudflare is an additional processing intermediary; obtain owner
acceptance of that route and its applicable terms before exposing the endpoint.
The URL is public, not an authentication secret. Webhook secret plus exact numeric
private-chat allowlist remain required. Do not use an interactive email challenge:
Telegram's webhook client cannot complete it. Do not expose the existing reviewer.

| Item | Proposed setting |
| --- | --- |
| Runtime | Exact runtime pin above; one foreground process/one worker |
| Inbound | Temporary tunnel to 127.0.0.1:8013, POST /telegram/webhook |
| Host check | Exact generated tunnel hostname, no scheme/path/port |
| Identity | One newly dedicated bot; owner user ID + private chat ID only |
| State | $HOME/axle-h13-owner-private/private.json and sibling pilot.sqlite3 |
| File policy | Directory 0700; config 0600; owner UID; umask 077 |
| Consent | Session only, one hour; no /save; invented text only |
| Paid budget | Two lifetime reserved attempts, one planned; no automatic retries |
| Admission window | 30 minutes maximum attended; stop earlier after first result |
| Stop policy | Graceful signal; retain process until actual drain; no auto restart |
| Evidence | Pass/fail, code pin, timings and aggregate counts; no raw messages/IDs |

The private directory must be on a local volume outside git, iCloud/Dropbox/other sync
and any backup selection. Inspect actual coverage first; do not alter global backup
settings. If a private excluded location cannot be verified, stop preparation. Disk
and OS backups are not covered by SQLite secure_delete. Same-user/privileged access
remains trusted. The proposed directory name is a plan, not an existing path.

## Decisions required before a launch request

Record privately: selected Mac/OS/Python, approved local directory, verified tunnel
binary version and distribution, dedicated bot identity, owner numeric binding,
provider account/model entitlement, applicable invented-input data-use authorization,
and an account spending ceiling accepted by B. Two attempts cap request count, not
dollars, output-token charges or account-wide use. No estimated dollar guarantee is
available. Meta compatibility remains unverified; the first approved case tests it.

Accept an attended retained-owner policy explicitly: caller waits and socket phase
limits are not a hard network deadline. At 30 minutes close new admission even if
work remains; drain can continue indefinitely. Do not run where sleep, terminal
closure, logout, reboot or a supervisor will kill/replace the process during drain.
At two minutes of incomplete drain, declare the test failed and escalate to manual
inspection; that threshold is an alert, not permission to kill. No deadline-killing
supervisor is part of this plan. If this policy is unacceptable, a separately
reviewed process isolation/deadline implementation is required before launch.

The launcher exposes no health/status endpoint or operator drain report. Its ordinary
logging is intentionally disabled. Readiness must be checked with the probes below;
successful normal launcher exit is the available completion signal. If field-level
live drain telemetry is required, implement it before approval rather than guessing
from process liveness. Installation/enrollment/webhook operator tooling is also not
implemented by this document: any helper must avoid token URLs/response payloads in
logs, disable automatic retries, validate acknowledgements and expose fixed errors.
Never put bot-token API URLs into curl arguments, shell history or browser address bars.

## Staged procedure after explicit authorization

1. Prepare a separate checkout at the runtime pin, verify git rev-parse HEAD matches,
   create a fresh venv, install requirements.lock.txt, and install this package with
   --no-deps --no-build-isolation after verifying setuptools is available. Record the
   actual Python/dependency inventory; do not silently upgrade pinned dependencies.
   Run the offline suite, pip check and exported reviewer schema check on that Mac.
   This validates the target environment before any credentials are supplied.
2. Create the dedicated bot through the owner's normal Telegram account. No groups,
   other testers or existing StarNet bot. Privately verify getMe matches the new bot.
   Verify getWebhookInfo has no existing webhook. An unexpected webhook means stop;
   do not delete someone else's integration.
3. With no webhook and no application running, owner sends a unique invented
   enrollment phrase in the private bot chat. A private operator helper uses
   getUpdates to verify from.id, chat.id, private type, is_bot=false and that phrase.
   Confirm the binding directly with B; no public identity lookup or raw JSON dump.
   Advance getUpdates offset beyond the observed update, and verify the enrollment
   update is acknowledged. No polling remains once a webhook is configured.
4. Verify the new state directory contains no existing pilot database or journal.
   Create private config locally through secure prompts/editor, never chat/git.
   Required fields: approved_synthetic_owner_test=true, provider_key, bot_token,
   webhook_secret, allowed_host, user_id, chat_id. Use a random secret with at least
   32 permitted [A-Za-z0-9_-] characters; IDs are exact positive integers below 2^53.
   The acknowledgement field records configuration, not owner permission.
5. Start the approved tunnel process toward http://127.0.0.1:8013 without starting the
   pilot yet. Record its generated hostname privately and complete allowed_host.
   Initial origin connection errors are expected. Review tunnel logging: no debug,
   HTTP body/header tracing or diagnostic uploads; use a private destination if any
   operational output is retained. Verify the chosen binary/flags against official
   docs. Do not assume the application's logging suppression controls the tunnel.
6. Launch the pinned venv Python in the foreground with only the config path supplied
   through AXLE_PILOT_CONFIG_FILE: python -m axle_hackathon.pilot_launch. Set no other
   mode/endpoint overrides. Record actual PID/start time privately, not by broad
   process-name matching. Keep the Mac awake through the attended test and drain.
7. Verify loopback and tunnel readiness using a small POST to /telegram/webhook with
   the configured Host and no webhook secret: expect fixed 403 rejected. Repeat
   locally with a wrong Host: expect 403. Verify the externally routed Host with the
   valid configured Host also yields 403 without secret; do not weaken Host checking
   to accommodate rewriting. These probes neither establish owner identity nor
   prove authorized processing. No health endpoint is claimed. If the tunnel changes
   Host unexpectedly, stop and review its configuration before registration.
8. Register setWebhook through the private helper: URL `https://GENERATED_HOST/telegram/webhook`, secret_token from private config, allowed_updates=["message"],
   max_connections=1, drop_pending_updates=true. The URL is one uninterrupted path.
   Dropping the fresh bot's pending enrollment/test updates is deliberate and needs
   owner consent. Validate ok=true/result=true and getWebhookInfo's exact URL and
   pending/error metadata without printing secrets. max_connections=1 reduces
   concurrent delivery; it is not a guarantee of message ordering or replay safety.
9. Owner sends a NEW /start only after registration completes. Follow prompts one at
   a time, waiting for each response. Use each current /reply nonce; do not paste a
   batch of commands. Fresh bot + drained backlog + fresh DB + sequential messages
   define this test's enrollment baseline. Edits, service updates, screenshots,
   unexpected update shapes or a decreasing/reused message ID end the test for
   inspection; do not reset the order fence. Bot pending retries can outlive a tunnel.
10. Choose session, then the invented case from the rehearsal: box_truck_26ft owned;
    payout 420, loaded 180, deadhead 40; reposition 20, hours 6, schedule feasible;
    target 2, all-mile planning CPM 1.25. Review and confirm the exact current revision,
    then /evaluate once as instructed. Expected: 240 miles, $300 planning cost,
    $120 reserve-adjusted planning surplus, NEGOTIATE. This is a hypothetical result,
    not accounting profit, route/HOS verification, a bid or native Muse integration.
11. On successful delivery, use /refresh once (no paid evaluation) then /forget.
    Observe its response. No result within 30 seconds, duplicate-looking result,
    malformed/unauthorized response, stalled privacy command or provider rejection:
    stop new commands and enter recovery. Do not spend the second attempt to debug.
12. Close admission and drain using the stop procedure below. Inspect only closed
    original storage for budget totals, update status counts, profiles count=0 and
    pending deletions=0. Compare with the private observation record. A failed or
    ambiguous send remains uncertain even if the provider charged it. Acknowledge
    any missing privacy completion before declaring pass.

The second lifetime attempt is reserved, not scheduled. Only after inspecting the
first outcome may B authorize a distinct new invented case with fresh confirmation
in the same intact database and remaining budget. A timeout never authorizes retry.

## Normal stop and rollback

Ask the owner to stop commands. Through the private helper deleteWebhook with
drop_pending_updates=true for this dedicated bot; validate success. Stop the tunnel
promptly even if that API call fails so public ingress is closed. Then send one
SIGTERM to the recorded pilot PID and wait for foreground exit. Repeated SIGINT or
SIGTERM does not force cleanup; no kill -9, terminal close, restart, reboot or launch
a replacement. Already admitted work can finish and send after public ingress closes.
Withdrawal cannot recall an already authorized external send.

Normal exit status 0 from this launcher's normal path follows all-true drain fields,
transport closure and storage release. An absent PID, nonzero exit, forced termination,
sleep/network loss or terminal disappearance is not equivalent evidence. Record the
actual launcher exit status. There is no rollback to an older executable against
uncertain live state; rollback here means retire this test route/process safely.

## Recovery decisions

| Event | Required action | Resumption rule |
| --- | --- | --- |
| Startup/probe/Host failure before registration | Close tunnel; stop launcher if present; inspect fixed error and private file modes | Correct setup only after clean exit; preserve any created DB |
| HTTP timeout/provider error/unknown send | Close webhook/tunnel; request graceful stop; retain owner while draining | No repeat evaluation; retain reserved attempt and uncertain records |
| /forget missing/stalled | Stop admission and commands; drain; inspect original closed DB | Deletion must be resolved before any fresh consent/test |
| Unsupported update/retry backlog | Remove webhook/drop pending on dedicated bot; close tunnel | Do not teach app to accept it by resetting IDs/state |
| Tunnel disconnect or hostname change | End the admission window; stop and drain | New URL requires reviewed config + webhook registration after clean stop |
| Drain incomplete after two minutes | Keep process and original files; record failed test; manual inspection | No automatic restart or forced kill |
| Crash/SIGKILL/forced stop | Close route/webhook; quarantine original state; assume in-flight outcomes uncertain | No relaunch under this plan; separate recovery review |
| DB missing/corrupt, old backup, unknown counter history | Keep offline; do not restore or create replacement DB | Retire experiment; later test needs independent approval and prior-attempt accounting |
| Accidental real data/secret exposure | Close route, drain, privately revoke affected credentials as authorized | No further model calls; handle external histories separately |

OS flock release after a crash does not prove external work completed. Never unlink
pilot.sqlite3.owner to bypass ownership. Do not open a second PilotInbox or worker to
inspect a live DB. After verified clean exit, a read-only SQLite inspection may use
aggregate queries only; no private profile JSON, claim/generation fields or IDs in
public evidence. If the database has an unexpected journal, stop; do not use an
immutable URI to bypass recovery. Restart mutates processing/sending to uncertain
and sessions are volatile, so launching is not an inspection method.

## Retention and closeout

No pilot DB backup or restore is planned for this disposable experiment. Verify that
policy before creating credentials. Preserve the intact DB, journal if present,
.owner file and private config during any unresolved incident. Do not copy individual
SQLite files while active. For an uncertain forced stop, the failed experiment stays
offline until an approved recovery or retirement decision; never reset counters.

After clean drain, completed /forget and aggregate inspection, retire the dedicated
webhook/tunnel. Revoke the dedicated bot token/provider key only if they were created
solely for this test and the owner approves that retirement. Remove private config
and pilot state within 24 hours of successful closeout, keeping only nonidentifying
pass/fail/count evidence. Removal does not guarantee SSD, OS snapshot, Telegram,
Cloudflare or provider erasure; external histories follow their own policies. A
failed /forget requires private operator remediation and confirmation, not a success
claim. Reusing the bot/account/DB later requires a new test decision and preserves the
historical attempt ledger; deletion is not a mechanism for gaining more attempts.

## Approval packet and evidence

Before execution, fill the private decisions above and obtain B's explicit approval
for the Mac/tunnel intermediary, dedicated bot/enrollment/drop-pending operations,
secret provisioning, at most two paid attempts under an accepted account ceiling,
retained-owner shutdown policy and retention. Merge is a separate decision and is
not necessary to run a specifically approved immutable feature commit.

Current approval packet is INCOMPLETE: target environment/tunnel version, bot/provider
account authorization and spending ceiling, private binding/location and secure
operator helper have not been verified. This plan can be reviewed now; do not treat
approval of this document as permission to skip those values or implementation gaps.
Repository [AGENTS.md](../AGENTS.md) explicitly requires separate owner approval for
merge, deployment, runtime/secret and infrastructure changes.

Evidence record: runtime pin, local Python/tunnel version, admission start/end, one
owner/one session, attempt count, expected vs actual canonical figures, refresh and
forget outcomes, exit status, aggregate privacy/queue counts, and pass/fail. Record
whether evidence was owner-operated live or offline; omit tokens, URLs with tokens,
chat/user IDs, raw messages, provider response IDs and private screenshots from git.
A live success demonstrates only this invented owner case. Real opportunities,
screenshots, invited carriers and public evidence permission remain separate work.

## Sources and document validation

Official references checked November 1, 2026:
- [Telegram Bot API](https://core.telegram.org/bots/api): getMe, getUpdates,
  setWebhook, getWebhookInfo and deleteWebhook; HTTPS, secret header, pending-update
  controls, allowed_updates and max_connections. Do not poll while webhook is set.
- [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/):
  temporary public hostname, changing URL, no uptime guarantee; interactive email
  authentication does not support non-interactive clients.

Documentation-only change. Internal links and runtime-pin/source facts checked;
whitespace checks passed. No new runtime tests or live operations were needed.
