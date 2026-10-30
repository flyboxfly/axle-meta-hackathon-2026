# H10 Deployment Evidence — Meta Hackathon Demo

Status as of October 30, 2026: owner-authorized public demo deployed and smoke-tested. This is a synthetic freight economics API for the hackathon closing November 4, not a production-readiness certification. Evidence below is owner-executed terminal output and Coolify screenshots supplied in chat; the author did not independently run VPS or authenticated HTTP checks. No credentials are included.

## Release identity

- Repository: flyboxfly/axle-meta-hackathon-2026.
- Deployed/pinned source: ef6baa65d9c6fed97daba83b1ad270aa9b5b0d13, branch main.
- GitHub comparison with H9 validation source dcc56cf028548289ac367b32a4e606a1d56b47da showed only docs/H9_DEPLOYMENT.md and docs/H10_COOLIFY_PREPARATION.md changed; runtime and packaging unchanged.
- Coolify 4.5.3; project Axle Meta Hackathon 2026; environment competition; application axle-meta-hackathon-api.
- Public base URL: https://axle-api-demo.flyboxfly.com.
- Owner added A record to 177.7.60.155, TTL 1 hour; public A lookup returned that address. AAAA result was not separately supplied.
- Application UUID: eocqau38t4sa5lkhoyvf61s4.
- Observed running container: aa70160b0d37, name eocqau38t4sa5lkhoyvf61s4-20261030T172705.
- Successful deployment log at 2026-10-30 17:27:37 UTC (13:27:37 EDT): new container healthy; rolling update completed. Helper stop logged next.
- No new pytest run for this documentation change. Prior owner post-H9-merge result remains 157 passed in 3.80s.

## Configured and inspected runtime

| Setting | Owner-observed evidence |
|---|---|
| Source/build | main pinned above; root context; /Dockerfile.remote |
| Deployment mode | Manual; previews disabled |
| Hostname | Only axle-api-demo.flyboxfly.com; HTTP to HTTPS enabled |
| Runtime variables | AXLE_API_ALLOWED_HOSTS=axle-api-demo.flyboxfly.com; AXLE_API_TOKEN present in UI; both runtime enabled, buildtime disabled; no values recorded here |
| Preview variables | Copies listed by Coolify; preview deployments remain disabled |
| User | 65532 |
| Read-only root | true |
| Dropped capabilities | ALL |
| Security option | no-new-privileges:true |
| PID limit | 64 |
| Memory | 268435456 bytes (256 MiB) |
| CPU | NanoCPUs=500000000 (0.5 CPU); quota/period fields 0 |
| Restart | unless-stopped |
| Logs | json-file, max-size=10m, max-file=3 |
| Host port bindings | {} |
| Mounts | [] |
| Networks | axle-meta-internal only |
| Process | python -m uvicorn axle_hackathon.remote_app:app --host 0.0.0.0 --port 8000 --workers 1 --lifespan on --no-proxy-headers --no-access-log |
| Healthcheck | CMD python /app/deploy/remote_healthcheck.py; interval 30s, timeout 5s, start period 15s, retries 3 |

One matching application container was observed. No model API key is required by this deterministic remote boundary. Token entropy, generation method, private storage, and equality of preview copies were not independently inspected. UI showed environment values in logs set to Hide all values.

## Public HTTPS checks

Executed from owner Mac, with normal TLS verification (no curl -k):

| Request | Observed result |
|---|---|
| GET /api/health over HTTPS | HTTP/2 200; {"status":"ok","synthetic_only":true}; Cache-Control: no-store |
| HEAD /api/health over HTTP | 307 Temporary Redirect; Location https://axle-api-demo.flyboxfly.com/api/health |
| POST /api/v1/axle/evaluate with {} and no token | HTTP/2 401; {"detail":"Unauthorized"}; WWW-Authenticate: Bearer; no-store |
| GET / | 404 |
| GET /docs | 404 |
| GET /redoc | 404 |
| GET /openapi.json | 404 |
| GET /api/v1/agent | 404 |
| GET /api/v1/freight/evaluate | 404 |
| GET /api/v1/browser/evaluate | 404 |

Authenticated tests used a hidden getpass prompt and Python urllib over HTTPS. Assertions passed for all three synthetic cases and no-store on each response:

| Target all-mile RPM | Decision | Revenue gap | Estimated cost | Surplus after allocated costs |
|---|---|---|---|---|
| 2.00 | NEGOTIATE | 60.00 | 290.00 | 130.00 |
| 1.75 | ACCEPT | 0.00 | 290.00 | 130.00 |
| null | NEED_MORE_INFORMATION | null | 290.00 | 130.00 |

Input: 26-foot box truck, payout 420, loaded miles 180, deadhead 60, diesel 4/gal, MPG 10, tolls 20, driver 80, maintenance .10/mile, equipment allocation 50, insurance allocation 20, operating hours 6, schedule feasible true; facts and benchmark confirmed, source screenshot. These H10 assertions did not separately check profile_id, model_invoked, or target revenue. Disabled-route output records status only, not bodies/headers or POST-method behavior. Successful authenticated requests support functioning Authorization forwarding, not byte-for-byte forwarding proof.

## Network and firewall observations

Network axle-meta-internal: bridge, Internal=true, IPv6=false; ID d28f3e70becc978e724f7014d7ac3261557c9309243be832e527f7d08b86cfd0; Linux bridge br-d28f3e70becc; subnet 172.16.3.0/24; host gateway 172.16.3.1. Proxy address observed 172.16.3.2, dynamically allocated (IPAMConfig={}), attached to coolify and axle-meta-internal. Shared proxy was not restarted; StartedAt remained 2026-10-17T12:09:14.791610765Z.

Initial probes showed host SSH and proxy ports reachable despite the internal network. Owner separately approved and applied:

1. iptables INPUT rule rejecting NEW traffic arriving on br-d28f3e70becc except source 172.16.3.2/32, comment axle-meta-block-host-new. Counter observed 1 packet / 60 bytes after SSH test.
2. Native nftables table bridge axle_meta_guard, forward hook priority -200, policy accept; rule matching incoming bridge br-d28f3e70becc, IPv4 source other than 172.16.3.2, ct state new, counter drop. Counter observed 4 packets / 240 bytes after proxy tests.

Host INPUT policy ACCEPT, FORWARD DROP; UFW inactive; DOCKER-USER empty. Kernel 6.8.0-147-generic, iptables v1.8.10 nf_tables; bridge and nf_tables loaded. bridge-nf-call-iptables sysctl absent. Native bridge rule syntax check passed before application.

Temporary hardened test backend received HTTP 200 from a disposable client sharing the proxy network namespace, proving proxy-initiated TCP and reply direction. Both test containers were removed by the scripted cleanup; no separate cleanup inventory was supplied.

Actual deployed container aa70160b0d37 subsequently produced:

| Destination | Result |
|---|---|
| 1.1.1.1:443 | OSError errno=101 (network unreachable) |
| 172.16.3.1:22 | ConnectionRefusedError errno=111 |
| 172.16.3.2:80 | TimeoutError |
| 172.16.3.2:443 | TimeoutError |

These are bounded destination-specific TCP checks, not proof of all egress or exfiltration resistance. DNS forwarding, other host services/addresses, IPv6 behavior beyond configured network flag, non-TCP protocols, peer access, and indirect paths were not exhaustively tested. Earlier host port 8000 probes timed out; cause was not established.

## Startup guard installed, not activated or reboot-tested

Owner approved a fail-closed hackathon startup design. Files installed:

- /etc/axle-hackathon/guard.nft (0600): separate inet axle_hackathon_host input chain at priority -10 rejecting NEW traffic from the Axle bridge; separate bridge axle_hackathon_bridge forward chain at priority -200 dropping NEW IPv4 traffic from that bridge. These startup rules have no proxy exemption.
- /usr/local/sbin/axle-hackathon-guard (0755): exits successfully if both named tables already exist; errors if only one exists; otherwise atomically loads the file. Table presence is not integrity validation of rules.
- /etc/systemd/system/axle-hackathon-guard.service: oneshot, RemainAfterExit=yes, Before=docker.service, WantedBy=multi-user.target.
- /etc/systemd/system/docker.service.d/axle-hackathon-guard.conf: Requires and After the guard service.

Owner ran systemd daemon-reload, enabled the guard, and verified units: enabled/inactive; Docker Requires/After included the guard; no verify errors supplied. No Docker restart or reboot occurred. The active temporary INPUT/bridge rules above remain the tested rules, distinct from startup tables.

nftables.service remains disabled/inactive; netfilter-persistent absent. /etc/nftables.conf contains flush ruleset and was left untouched. Do not enable it or save/replay all Docker-managed firewall state.

Operational limitation: after reboot, new proxy-to-Axle connections will be blocked until a reviewed manual exemption for the verified current proxy identity/address is restored. No executable recovery/unlock procedure has yet been tested. Rule ordering across old/new tables must be considered; adding an exemption in one table does not override another table's drop. Bridge recreation can change its identifier. A dynamically reassigned exempt IP is not a durable identity boundary.

Rollback of installed startup integration (requires owner authorization): remove only the named Docker drop-in, disable the guard service, daemon-reload; separately review removal of the two startup tables if present. Do not flush the global ruleset. No rollback or recovery drill executed.

## Build helper failure and temporary workaround

First Coolify deployment failed before image build: git ls-remote could not resolve github.com. Host getent resolved GitHub successfully. Debug log confirmed helper image docker.io/coollabsio/coolify-helper:1.0.19 launched with --network axle-meta-internal, --rm, Docker socket and buildx mounts.

Builder selection offered only Deployment server; no separate build servers connected. Owner ran a bounded watcher while retrying only this deployment. It selected the single running helper by image and attached it to Docker's default bridge. Output confirmed temporary helper connected. Deployment then succeeded; helper kpfteyoydfbqf48aglgpgs74 was stopped by Coolify. Additional network disappears on helper removal, but an independent post-cleanup listing was not supplied.

This manual workaround is not a durable build pipeline. Do not attach the runtime to an internet-capable network. Before reuse, verify the exact helper belongs to this deployment; image-only selection is insufficient if other deployments are active.

The historical H9 image was absent from the current daemon. Owner located /tmp/axle-h9-build.qrWgPL/repo at dcc56cf028548289ac367b32a4e606a1d56b47da and rebuilt it. Build and pip check succeeded; reported image ID sha256:38491267dbad220256a9e8e1b6a337c33fd6da5978c388a55a8dc1fb262c2d00, linux/amd64, User=65532. This is not the deployed application image ID; no application image digest was captured.

## Scope and remaining checks

Owner explicitly approved the resource configuration, hostname, firewall changes, startup design, and public deployment in this session. Keep scope aligned with November 4 hackathon synthetic demo.

Verified: public health/TLS client acceptance/HTTP redirect, missing-token rejection, three canonical authenticated outcomes, disabled-route GET status codes, inspected container controls and tested TCP restrictions.

Still unverified or deferred: reboot/recovery and IP reassignment, application image digest, exact build-context allowlist/sentinel verification and honored ignore-file evidence, vulnerability scanning, representative load, rate/concurrency/oversize/slow-body abuse checks, public wrong-token/Host/Origin tests, effective proxy body/time limits and complete logging/redaction review, certificate renewal/TLS cipher policy/HSTS, stop/revocation drill, independent helper cleanup check. Historical shared-proxy pending changes remain unexplained and untouched. No new installs, scanners, broad traffic tests, or production hardening are claimed.

No model/Meta call is made by this remote economics boundary. H11 should integrate the working Meta/Muse workflow with this authenticated API, preserving deterministic calculations and synthetic-only scope. Do not treat this evidence as completion of every historical H8/H9 proposed production gate.

## Stop and handoff

Stop only axle-meta-hackathon-api in Coolify for immediate suspension. Verify no running competition container and no application success response; proxy 502/503 alone is not the app serving. Rotate token and restart/redeploy if compromise suspected. Do not restart the shared proxy or alter unrelated workloads.

This evidence PR changes documentation only. Merging it must not redeploy: retain the existing pinned runtime SHA until a separately authorized release change.
