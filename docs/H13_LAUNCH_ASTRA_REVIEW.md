# H13 launcher Astra review

November 1, 2026. Reviewed baseline d080577. Offline source and tests only.
No listener, live transport, credentials or infrastructure changes.

## Findings and fixes

1. The pinned Uvicorn 0.54.0 Server.capture_signals implementation restores prior
   handlers and re-raises captured signals when serve exits. A normal SIGTERM could
   terminate the process before the launcher's finally block inspects drain. The
   launcher now owns SIGINT/SIGTERM for the complete serve-and-drain lifetime and
   disables Uvicorn signal capture/replay in its dedicated subclass. Repeated graceful
   signals request exit without force_exit; handlers restore after drain. Launch is
   restricted to the main thread. This is intentionally allowed to wait indefinitely.
2. Uvicorn can return after failed lifespan startup without raising. The launcher
   now checks server.started and raises a fixed failure after cleanup, allowing main
   to return nonzero rather than report success.
3. A config file growing between fstat and read could exceed the advertised 8 KiB
   limit. The reader now checks the actual bytes before parsing as well as stat size.

Regression coverage simulates first SIGTERM during serve and repeated SIGINT during
cleanup, prohibits signal replay, verifies prior-handler restoration, and exercises
both successful and failed startup. A separate case simulates config growth after
stat. Server execution and signal registration are mocked; this does not establish
real process-manager shutdown behavior. Existing repeated-incomplete-drain test stays.
Full suite: 363 passed in 5.17s. pip check, reviewer OpenAPI and diff checks passed.

## Review conclusion and remaining gates

The reviewed code is suitable for preparing an isolated synthetic owner-test plan,
not a live launch approval. No further model-switch review loop is necessary for
this slice. The next deliverable is a concrete deployment/recovery plan using an
immutable reviewed commit, with the owner selecting/authorizing the isolated host,
bot/account and provider data-use terms before any secrets or live work.

Python threads and socket phase timeouts do not provide a hard total execution
limit. SIGKILL, explicit task cancellation, interpreter failure or forced process
termination can still interrupt drain. A supervisor must not automatically replace
an owner while work is unresolved; forced-stop recovery needs separate review.
Transport close can still block. The current launcher deliberately favors retained
ownership over bounded process exit and does not solve those operational questions.

Private-file checks assume trusted same-user filesystem access; they are not a
sandbox against privileged access, hostile ancestor replacement or hard links.
Global Python logging suppression is appropriate only to this dedicated process;
it does not control external proxy/provider/Telegram histories or process crash dumps.
Inbound connection saturation can reject privacy commands, and SQLite latency is
still synchronous. Controlled enrollment/message-order baselines and backup/deletion/
attempt-counter restoration remain open. Live API compatibility is unverified.

No merge, deployment, paid call, live message or real carrier input is authorized by
this review. Existing synthetic reviewer service and shared Coolify proxy stay unchanged.
