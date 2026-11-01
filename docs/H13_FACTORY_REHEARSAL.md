# H13 fixed composition and offline rehearsal

Follow-up: [configuration review and owner-test plan](H13_FACTORY_ASTRA_REVIEW.md).

October 31, 2026. Baseline c31e995. Invented records and fake HTTP transports only.

build_synthetic_host composes the reviewed HTTP clients, direct Responses adapter,
Telegram sender, PilotDelegator, lifecycle owner and ASGI host. Construction does
not start scheduling or make a request. There is no environment loader, command-line
launcher, socket listener, webhook registration or credential provisioning.

Configuration is fixed: separate model/sender clients with one/two connections,
zero transport retries, no redirects or ambient environment proxies. Model phase
limits are connect 3/read 10/write 3/pool 1 seconds, elapsed acceptance check 15,
caller wait 20. Sender limits are connect 2/read 3/write 2/pool 1, elapsed check 4,
existing delivery caller wait 5. Scheduler interval is 1 second, host scheduler-join
wait 6 seconds. Caller supplies explicit global/per-carrier lifetime attempt caps,
approved numeric bindings, storage path, disclosure policy, allowed host and secrets.
No endpoint overrides or injected clients are factory parameters. Tests substitute
client creation internally with MockTransport. PilotDelegator still rejects anything
except synthetic/hypothetical opportunities; the text intake explicitly asks for
invented figures. Typed free text can still contain private data, so real users must
not be invited under unresolved provider terms.

The factory closes all created clients on construction failures, including failed
second-client creation and failed database acquisition before lifecycle cleanup.
It reports fixed construction-failure text and attempts each client. A close failure
cannot guarantee reclamation; no successfully returned owner exists in that path.
After successful construction clients belong to the lifecycle and close only when
all execution/request drain fields are true. No global logging settings are changed.
Final hosting must disable HTTP request/response/debug logging and traceback-local
capture, since Telegram token URLs and provider headers exist in transport objects.

The new full rehearsal uses TestClient lifespan and the real scheduler: /start,
session consent, owned 26-foot box truck, invented $420 payout/180 loaded/40 deadhead/
20 reposition miles, 6 hours feasible, $2 revenue target and $1.25 all-mile planning
CPM. It confirms revision 1, queues evaluation, observes one model HTTP request and
canonical NEGOTIATE with $300 planning cost in a fake Telegram send. Repeated update
9 does not call the provider again. /forget clears active consent, and shutdown drains
and closes both clients/storage. Other cases verify both constructor failure paths.
Full suite: **354 tests pass**. Dependency, reviewer OpenAPI and diff checks pass.

## Proposed owner-test gates

1. Review this composition and rehearsal. Confirm live provider API compatibility and
   account data-use terms before choosing an authorized test mode. Real opportunities
   remain unsupported by the synthetic-only delegator.
2. Resolve hard network cancellation/deadline policy. Phase timeouts and between-read
   elapsed checks cannot interrupt stalled I/O; wrappers retain capacity and ownership.
   Document how an embedding process retains/inspects incomplete drain before any
   restart or database reopening. No hard process deadline is claimed.
3. Prepare a dedicated bot, one approved owner binding, isolated private storage and
   dedicated service. Specify controlled message-ID enrollment/reset, backup/deletion
   restoration, log retention, inbound connection/body limits and SQLite latency policy.
   Do not repurpose the StarNet bot or production database. Select/check a host name
   only during approved hosting preparation; no DNS or hostname is provisioned here.
4. Produce a concrete deployment pin, private secret injection, rollback and owner-only
   synthetic smoke-test checklist before asking for deployment approval. Keep the shared
   Coolify proxy and all protected production infrastructure untouched. If isolated
   routing needs those protected changes, present a separate hosting choice.
5. Only after owner workflow evidence and data-use clearance consider other testers,
   real-data extraction, UX improvements, brand integration and public demo evidence.

No paid calls, real records, live messages, credentials, merge, deployment or
infrastructure changes occurred. This is offline integration evidence only.
