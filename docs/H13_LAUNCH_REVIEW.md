# H13 isolated launch candidate

Follow-up: [owner-test deployment and recovery plan](H13_OWNER_TEST_DEPLOYMENT.md).

November 1, 2026. Baseline 2e7a81e. Offline tests only; launcher not executed against
a listener, live provider or bot. No credentials or runtime configuration created.

pilot_launch is a dedicated-process entry point around the fixed synthetic factory.
It reads only AXLE_PILOT_CONFIG_FILE (a path, never a token argument). Config must be
an absolute path in an owner-owned mode-0700 directory, with an owner-owned regular
mode-0600 file, max 8 KiB, no final symlink and no duplicate JSON keys. Unknown fields
are rejected. Required fields are approved_synthetic_owner_test=true, provider_key,
bot_token, webhook_secret, allowed_host, user_id and chat_id. Numeric IDs must be
exact positive integers below 2^53. The acknowledgement field is configuration, not
permission from the owner or proof of provider data-use clearance.

Storage is fixed to pilot.sqlite3 beside that config. A private umask is set before
construction. There is one owner binding, global/carrier lifetime cap 2, fixed client
settings and synthetic-only delegation. The private-directory checks assume a trusted
POSIX host; they do not defend against hostile ancestor replacement, hard links or
privileged access. No secrets/config sample is written into the repository.

The launcher disables Python logging process-wide before constructing HTTP clients,
and prints only a fixed launcher error on ordinary failure. It is intended for a
dedicated process, not embedding in production apps. It uses Uvicorn's installed
Config API: 127.0.0.1:8013, one worker, reload/proxy headers/access logs disabled,
WebSockets disabled, concurrency/backlog 16, keepalive 2 seconds, incomplete h11
header buffer 8 KiB and graceful server wait 6 seconds. No public socket/TLS/proxy,
DNS or webhook registration is configured. Network exposure still needs an approved
isolated route; loopback binding alone is not a Telegram deployment.

After server exit it repeatedly inspects owner.close off-loop, waiting one second
between incomplete/failed attempts. It returns only after all drain fields report
complete, retaining the owner otherwise. This can wait indefinitely for hung I/O or
client cleanup. Graceful SIGINT/SIGTERM handling now remains installed through drain, without
signal replay or a second-signal fast exit. Forced process-manager termination,
SIGKILL and event-loop teardown can still interrupt it. No hard total network/process deadline is claimed. SQLite
still executes synchronously in the webhook handler. The connection limit bounds
all inbound traffic and can reject /forget during total connection saturation; the
separate conversation slots preserve privacy admission only within that host limit.

Six new cases verify valid private config, permissions/symlink/approval/duplicate-key
rejection, fixed loopback/single-worker settings and repeated drain inspection. Full
suite: 360 tests pass. Dependency, reviewer OpenAPI and diff checks pass. Tests replace
server execution; no socket or live transport is used.

## Packaging and owner-test preparation

The package source is this feature branch plus requirements.lock.txt; use an approved
immutable commit, Python 3.11+ and a fresh isolated venv. No installation or process
startup is performed by this change. Entry point after explicit approval is
python -m axle_hackathon.pilot_launch with the private config-file path supplied only
through AXLE_PILOT_CONFIG_FILE. Do not run the generic synthetic reviewer service as
the pilot or share its credentials/database. Do not put real config in git/chat.

Before asking for launch approval, review this candidate and resolve total-deadline
and termination policy, data-use/account authorization for invented owner inputs,
controlled binding/message-order enrollment, storage backup/deletion restoration,
and synchronous storage latency. Record an immutable package pin, the actual isolated
host/routing arrangement, secret-file provisioning and rollback. Do not change the
shared Coolify proxy, VPS/Docker/network/firewall or production app/database.

Rollback is to stop new admission and let tracked operations drain, then retire the
dedicated pilot process and its approved routing. Do not reset attempt counters or
restore an older database to retry uncertain tasks. An incomplete drain requires
retaining the process/owner or an explicitly reviewed forced-termination recovery
procedure; this candidate does not supply one. Follow H13_FACTORY_ASTRA_REVIEW.md
for the exact invented-input smoke test after approval.

No merge, deployment, secret provisioning, paid calls, live messages or infrastructure
changes. This package remains a review candidate; real-data pilot support is separate.
