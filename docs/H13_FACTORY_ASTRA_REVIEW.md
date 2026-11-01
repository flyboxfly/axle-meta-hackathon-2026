# H13 composition review and owner rehearsal plan

Follow-up: [isolated launch candidate](H13_LAUNCH_REVIEW.md).

November 1, 2026. Reviewed draft 74b4622. Offline assistant review; not an independent
audit or live-provider validation.

## Review outcome

No additional production-code change was identified in this focused factory review.
The previous full rehearsal replaced create_http_client with bare mock clients, so
it demonstrated orchestration without exercising the factory's actual HTTP settings.
The rehearsal now calls the real client builder and substitutes only HTTPTransport.
It checks the outgoing phase-timeout extensions, separate one/two connection limits,
zero transport retries, disabled ambient environment settings and disabled redirects.
The full host/scheduler/intake/provider/sender/withdrawal/shutdown flow still runs.
This improves integration evidence; mock transports do not prove socket timing.

The factory has no user-selectable provider endpoint or real-data mode, transfers
client ownership on success, and attempts client cleanup on failures before/after
inbox acquisition. Its fixed-error boundary avoids exposing raw construction errors.
Cleanup failures are not successful reclamation and must not be reported as such.
No code paths in this review grant merge or deployment permission.

## Proposed owner-only live smoke test — not executable yet

Scope: one owner, one private Telegram chat, one dedicated bot, invented text inputs,
session-only consent, no screenshots/real load boards/other testers, no persistent
profile save. Proposed caps: global 2 and carrier 2 for the entire test database;
first attempt is the planned case, the second is reserved for an explicitly chosen
new case after inspecting any failure. No automatic replay/reset of budget counters.

Before approval, produce a reviewed launcher/package pinned to its final commit,
with explicit one-process/one-worker startup, private directory permissions, access
and HTTP debug logging disabled, no traceback-local capture, bounded inbound admission,
and a shutdown policy that retains the owner until drain or documents forced-process
termination uncertainty. Configure the fixed factory through private server-side
secrets; never put tokens in chat, git, shell history, screenshots or command arguments.
A hostname, service, secret path and bot are not provisioned or selected by this doc.

Use an isolated service/storage and dedicated bot. Do not change the shared Coolify
proxy, production app/database, Docker daemon, VPS network/firewall or StarNet bot.
If isolated routing cannot be provided without protected changes, choose another
hosting arrangement before requesting approval. No new paid hosting is authorized.

Required decisions before the smoke test:
- Actual outbound total-deadline/process policy. Current per-phase socket limits,
  elapsed acceptance checks and caller waits do not forcibly cancel running I/O.
- Provider-account permission for the intended invented-data test, credit/billing
  ceiling and live Responses compatibility; no live compatibility is established.
  Real-data provider clearance is a separate gate and does not make this synthetic
  implementation support real opportunities.
- Approved owner user/chat IDs, fresh enrollment/message-order baseline, disclosure
  text, and how residual Telegram/provider messages and host metadata are retained.
- Pilot storage backup/restore policy: restored counters/deletion state must not
  silently authorize replay or resurrect withdrawn records. No production backups
  are changed; a disposable test dataset still requires a documented recovery rule.
- A concrete deployment pin, host/proxy isolation, secret injection, rollback and
  stop procedure for the owner to approve. This checklist alone is not that approval.

After those decisions and explicit live authorization, use this exact sequence:
1. Confirm the dedicated service is healthy and only the approved private chat enters.
2. /start; choose session. Enter box_truck_26ft owned; 420 180 40; 20 6 feasible;
   target 2; all-mile cost 1.25. Review every invented value before confirmation.
3. Confirm the displayed step, then /evaluate once. Expected: 240 total miles,
   $300 planning cost, $120 planning surplus, NEGOTIATE under supplied assumptions.
   Observe one provider attempt and one result delivery; an uncertain result is not
   permission to repeat the same paid command.
4. /refresh should recover the current prompt without another paid evaluation.
5. /forget should revoke active consent; verify cleanup with approved metadata-only
   operator evidence. Do not use public screenshots containing chat IDs or tokens.
6. Stop admission, inspect all drain fields, close clients and storage. If incomplete,
   retain the owner; do not reopen the database or register a replacement worker.
7. Record pass/fail, revision and counts only. A successful owner smoke test does not
   validate other carriers, real data, general reliability or economic outcomes.

## Immediate next implementation

Prepare the isolated launcher/package and operational policy offline, resolving
outbound deadline and inbound/storage latency behavior before live approval. Keep
real-data extraction and external tester enrollment outside this synthetic slice.
The November 4 submission should distinguish the offline workflow from any later
owner-observed live evidence, and retain the pre-existing concept/brand disclosure.

Validation: 354 tests passed; dependency check, reviewer OpenAPI compatibility and
whitespace checks passed. No live requests, credentials, merge, deployment or
infrastructure changes. This update changes tests and documentation only.
