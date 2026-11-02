# H13 private setup helper candidate

November 1, 2026 (America/New_York). Offline implementation on deployment-plan baseline
9c5bdce. No live setup, credentials, bot calls, tunnel, listener or model request.

The dedicated module pilot_setup provides prepare, check, register and remove commands.
It shares the direct HTTP client builder and bounded/sanitized JSON adapter. Imports
have no file/network effect. main requires an interactive terminal, disables Python
logging process-wide and applies umask 077. Private inputs use getpass without echo;
no token, IDs, provider key or enrollment phrase is accepted as a command argument.
The only config input from the environment is AXLE_PILOT_CONFIG_FILE.

## Behavior

prepare requires the explicit local acknowledgement PREPARE NEW OWNER TEST. Prompts
collect the dedicated token, expected bot username (without @), provider key, generated
Quick Tunnel hostname, approved owner user/private-chat IDs and a 16–128 character
unique phrase already sent to that bot. getMe must confirm the token's numeric bot ID,
bot status and expected username. No public lookup or raw response is printed.

Enrollment requires no webhook, a bounded nonempty batch smaller than 100 updates,
only the approved private nonbot user/chat, exactly one matching phrase, and distinct
integer update IDs. A second webhook check precedes a single getUpdates acknowledgement
past the highest received update ID. Any remaining updates fail closed. Unknown or
foreign records are not acknowledged by this helper. Races with another operator,
new messages or external webhook registration are not transactionally prevented:
one operator, owner silence during setup and fresh dedicated bot remain assumptions.
Acknowledging updates is an external mutation and must be authorized before execution.

prepare then writes only a NEW config in an existing owner-owned 0700 directory, mode
0600 with O_EXCL/O_NOFOLLOW and fsync. Existing config, final symlink or pilot.sqlite3*
state artifacts cause rejection; no overwrite/reset command exists. It generates a
random webhook secret. A partial failed write remains for private inspection, not an
automatic retry. Parent filesystem assumptions match the launcher; no hostile same-user
or ancestor-race defense is claimed. The helper does not create the directory, choose
backup exclusions, verify OS privacy or launch anything. Provider key syntax is checked;
provider permission, balance and compatibility are not probed.

check verifies bot identity and webhook scope, then prints only configured yes/no,
pending count and whether an error timestamp exists. It never prints raw error text,
URLs, usernames, chat IDs or API responses. register/remove require typed REGISTER or
REMOVE and the stored private config. register requires an EMPTY current webhook;
even a matching existing registration is rejected to avoid dropping pending updates
on a repeated invocation. It uses the exact HTTPS host/path, secret header value,
allowed_updates=[message], max_connections=1 and drop_pending_updates=true; strict
true acknowledgement and matching webhook metadata are required. remove rejects a
foreign URL and uses deleteWebhook with drop_pending_updates=true, then verifies an
empty URL and zero pending count. Removing an already-empty scoped webhook still
intentionally discards its pending updates. No automatic mutation retry is provided.

Only fixed official Telegram endpoints/methods are allowed. Response acceptance is
bounded to 64 KiB and five seconds checked between chunks; HTTP phase limits remain
connect2/read3/write2/pool1 with one connection, no transport retries, redirects or
ambient proxies. These are not a hard wall-clock kill for stalled I/O. Ordinary CLI
exceptions and Ctrl-C print one fixed uncertain-outcome message and exit 1. A lost
acknowledgement can mean registration/removal/enrollment already occurred. After a
failure use approved private inspection, not repetition; stop the tunnel independently
if ingress must close. No bot-token revocation or deletion of state is automated.

## Operator entry points after approval

Use a new reviewed immutable package containing this module; the earlier runtime pin
ab020af lacks it. Record that combined package pin in the private approval packet.
Supply the absolute config path via AXLE_PILOT_CONFIG_FILE without placing secret
values in shell history. Commands are:

- python -m axle_hackathon.pilot_setup prepare
- python -m axle_hackathon.pilot_setup check
- python -m axle_hackathon.pilot_setup register
- python -m axle_hackathon.pilot_setup remove

Directory preparation and tunnel acquisition happen locally after authorization.
prepare needs the tunnel hostname but no running app. register follows a running
pilot and successful readiness probes. check can inspect an uncertain webhook change
without replaying it. No command starts the pilot, sends a chat message or calls Meta.
Typed acknowledgements are local operator guards, not proof of owner authorization.

## Evidence and remaining work

16 new offline cases cover exact enrollment/ack offset, foreign/bool identity,
wrong phrase, existing webhook, unexpected acknowledgement backlog, exact registration
parameters, refusal to replace, scoped removal, exact boolean acknowledgement,
sanitized no-retry transport failure, exclusive private-file preservation, symlink/
permissions rejection, hidden-input CLI composition and nonterminal refusal.
HTTP responses are MockTransport streams; no listener or external call is used.
Full suite: 379 passed in 5.61s. pip check, reviewer OpenAPI and whitespace checks pass.

Review this security-sensitive helper before live execution. Still unverified:
owner Mac/Python/tunnel inventory, backups/private location, provider authorization
and dollar ceiling, actual bot binding, target-host forwarding and process-manager
shutdown. The [deployment plan](H13_OWNER_TEST_DEPLOYMENT.md) retains those gates.
No merge, deployment or live permission is implied. No new framework/dependency.

API shapes checked against the [official Telegram Bot API](https://core.telegram.org/bots/api)
on November 1, 2026: getMe, getWebhookInfo, getUpdates, setWebhook and deleteWebhook.
