# H10 Coolify Preparation — Deployment Proposal Only (Not Deployed)

Status: proposal only. No Coolify resource created, no secret generated or
stored, no DNS changed, no deployment or public exposure performed, no
commands or tests run by Muse in authoring this document. No application
source or existing file changed; this document is the only H10 artifact.
Owner read-only VPS and Mac checks occurred during H10 and supplied the
§1 evidence.

- Expected branch: `h10-coolify-preparation`.
- Base/source baseline: full SHA
  `c28666b92e7fa71a43e5c0c8a8745c125779a2d4`.
  The final deployment SHA must be reselected after any approved H10 merge.
- Predecessors: [H8 remote design](H8_REMOTE_DESIGN.md) (enforced boundary),
  [H9 deployment packaging](H9_DEPLOYMENT.md) (image, lock, probe, VPS
  validation). H8/H9 behavior, canonical economics, and H1–H7 functionality
  are preserved.

## 0. Proposed values (all unapproved, unconfigured)

| Setting | Proposed value |
|---|---|
| Application | `axle-meta-hackathon-api` in a dedicated competition project/environment, separate from local demo and production workloads |
| Hostname | `axle-meta.flyboxfly.com` (proposed, not approved/configured; no DNS change made) |
| Build | `Dockerfile.remote`, repository-root context, source baseline above |
| Deployments | Manual only; automatic and preview deployments disabled |
| Internal port | 8000; no public host-port mapping |
| Workers / replicas | One Uvicorn worker (image `--workers 1`) and exactly one replica (H8 limiter is per-process) |
| Runtime env | `AXLE_API_TOKEN` (runtime-only secret) and `AXLE_API_ALLOWED_HOSTS=axle-meta.flyboxfly.com` only |
| Excluded | No model key, no demo token, no storage, no database, no mounts |
| Resource limits | CPU 0.5, memory 256m (H9 ran under these limits; representative load remains unverified) |
| Identity / command | Preserve image `USER 65532` and image command |
| Custom Docker Options | `--read-only --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 64` (proposed; verify generated configuration and resulting container after separate authorization; installed-version support not proven) |
| Health check | Preserve image Python HEALTHCHECK with explicit allowed Host (current official docs describe Dockerfile-check precedence; installed-version behavior pending verification) |
| Restart policy | `unless-stopped` (proposed; confirm platform support) |
| App log rotation | Bounded 10m / 3 files (proposed; provisioning method and actual logging behavior unresolved) |

Official documents below are current guidance only, not proof of behavior
on the installed version:

- <https://coolify.io/docs/applications/configuration/health-checks>
- <https://coolify.io/docs/applications/builds/custom-docker-options>
- <https://coolify.io/docs/applications/configuration/resource-limits>

## 1. Evidence versus proposed settings versus unresolved checks

Owner-observed evidence (as supplied; Muse ran no commands in authoring;
owner read-only VPS and Mac checks occurred during H10):

- Coolify image `coollabsio/coolify:4.5.3`, running.
- Running Traefik `3.6.25`, linux/amd64.
- Proxy attached network: `coolify`.
- Proxy Docker logging: `json-file`, `max-size=10m`, `max-file=3`.
- Running-proxy command filter returned no explicit `accesslog`,
  `log.level`, or entrypoint `respondingTimeouts` flags. This does not
  establish effective settings from other sources (file, env, defaults).
- Dashboard shows “Changes pending” / proxy restart required. Pending
  changes are unexplained; do not restart the shared proxy.
- H9 isolated Linux validation succeeded; test container removed.
- Owner post-merge tests: 157 passed in 3.80s.
- No competition service, hostname configuration, token issuance, DNS
  change, or public deployment has occurred.

Proposed but not configured: every row in §0, including the hostname,
resource creation, secrets, DNS, TLS/proxy behavior, health-check handling,
custom Docker options, restart policy, and log rotation.

Unresolved until separately authorized and evidenced: effective proxy
settings from all sources; installed-version support for custom Docker
options, restart policy, and Dockerfile-check precedence; TLS, Host/
Authorization/Origin forwarding, redirects, body limits, timeouts, error
shapes, and logging behavior; build-context allowlist contents; egress
controls; vulnerability/abuse posture; representative load; the unexplained
pending proxy changes; and the final deployment SHA.

## 2. Runtime-only token provisioning and revocation (procedure only)

No token is generated here and no secret is embedded in this document.

- Generate: owner generates one value offline (for example
  `secrets.token_urlsafe(32)`) on the owner machine. Never commit, paste
  into chat/issues/docs, or reuse a local demo token.
- Store: owner stores the value in the owner secret manager only.
- Provision: owner sets `AXLE_API_TOKEN` plus
  `AXLE_API_ALLOWED_HOSTS=axle-meta.flyboxfly.com` as runtime-only Coolify
  environment for `axle-meta-hackathon-api`. Nothing secret is baked into
  the image. Startup fails closed without valid values (H8 lifespan).
- Verify: after an approved deployment only, `GET /api/health` (host
  allowed, no auth), then one authenticated
  `POST /api/v1/axle/evaluate` over HTTPS (§7).
- Rotate: generate a new value, update the secret manager and Coolify
  runtime env, redeploy/restart. No hot reload; restart required.
- Revoke/suspend: replace the token and restart all instances (old value
  then returns 401), or stop the app for immediate suspension. Unsetting
  the token prevents startup. Single shared reviewer token only; per
  reviewer tokens remain follow-up work.
- Compromise: revoke and rotate as above, review proxy access metadata for
  the exposure window (status codes and timestamps only; no bodies), and
  notify reviewers out of band.

## 3. TLS, forwarding, redirects, limits, errors, logging (validation plan)

Do not invent confirmed defaults. Each item states what to verify after
separate authorization; none is verified in H10.

- TLS: terminate at the platform proxy; authenticated clients use HTTPS
  directly to the competition hostname and never send credentials over
  plain HTTP. Verify certificate issuance/renewal, accepted
  versions/ciphers, HSTS presence and value, and that plain-HTTP behavior
  (reject or redirect) matches the approved choice. The app serves plain
  HTTP to the proxy only and terminates no TLS.
- Host: proxy must preserve the original `Host` unchanged to the app (H8
  enforces `request.url.hostname` against the allowlist; `--no-proxy-headers`
  means `X-Forwarded-*` are ignored). Verify the app sees
  `axle-meta.flyboxfly.com` and that no internal-name override breaks
  legitimate requests into 403.
- Authorization/Origin: proxy must not strip `Authorization` or `Origin`;
  stripping would break auth or Origin-denial semantics. Verify both reach
  the app byte-identical.
- HTTP redirects: test plain-HTTP redirects only without credentials or
  sensitive bodies. Verify the exact redirect (status, `Location`, whether
  method/body survive) for `http://` requests. A redirect does not protect
  credentials already sent over HTTP.
- Proxy body limits: propose at or below the app 32 KiB limit; exact value
  unset. Verify which layer rejects oversize first, the exact status/body
  returned, and that oversize never reaches evaluation.
- Proxy timeouts: connection/header/body timeouts at the proxy in front of
  the app's 10 s body-read deadline; exact values unset. Verify values from
  every configuration source (flags, files, env, defaults) and observe
  behavior on slow headers/body; the app deadline covers only its body read.
- Proxy errors: record the exact shapes for backend-down, timeout,
  oversize, and rate-limit cases (for example Traefik/Coolify pages or
  empty responses). Attribute each response to a producing layer only with
  supporting evidence; otherwise mark the producing layer unknown. Do not
  treat every non-H8 shape as necessarily proxy-generated.
- Logging: the app emits no request logs and Uvicorn access logging is
  disabled, but Uvicorn error/startup logs may carry tracebacks and the
  proxy may log access metadata. Verify proxy log settings (access/error,
  level, retention), the app-container log capture and the proposed 10m / 3
  rotation provisioning, and that no bodies, tokens, or submitted facts are
  recorded. Disabled access logging does not imply redacted
  infrastructure logs.

## 4. Egress and isolation options (proxy connectivity required)

- The shared `coolify` network attachment is connectivity evidence, not
  proof of isolation.
- `--network=none` (H9 §4D) proved loopback serving with no egress path; it
  is not a deployable proxy-network solution because the proxy must reach
  the app.
- Scoped proposal: attach `axle-meta-hackathon-api` only to the minimum
  proxy-reachable network required for ingress; no published host ports; no
  host mounts; read-only root filesystem, all capabilities dropped,
  no-new-privileges, PID limit (§0 options, support unverified). The app
  needs no outbound traffic for evaluation, so deny-by-default egress is
  preferred, but the provisioning method on this platform is unresolved
  and remains a deployment blocker. Unverified or absent egress controls
  do not satisfy the existing H8/H9 requirements.
- Required evidence (after authorization): generated container/network
  inspection showing exactly the expected attachments and options; a bounded
  disposable-exec check that ingress from the proxy succeeds while outbound
  attempts fail closed; no exfiltration payloads, no external writes.
- Do not recommend changing shared firewall or proxy settings without
  separate review, and never as part of creating this app. The unexplained
  pending proxy changes and restart requirement stay untouched.

## 5. Build-context allowlist validation plan (synthetic sentinels only)

- Build proposal: `Dockerfile.remote` with repository-root context from the
  reselected deployment SHA. Which ignore file the platform builder honors
  (`Dockerfile.remote.dockerignore` versus root `.dockerignore`) is
  unverified and must be confirmed first.
- Plan (after authorization, on a disposable branch/workspace; never with
  real secrets): add synthetic sentinel files with random marker contents
  at must-exclude paths (for example a fake dotenv-named file, plus
  sentinels under `tests/`, `fixtures/`, `docs/`, and beside the full
  local lock); trigger the platform's context preparation; list the exact
  transferred context and assert every sentinel is absent while exactly the
  allowlisted inputs (Dockerfile, remote lock, probe, five modules, parent
  dirs) are present; assert the built image contains none of the sentinels;
  then delete all sentinels. A small transferred-context size alone does not
  prove exact contents.
- Never place real secrets, tokens, or keys in the workspace for this check.

## 6. Vulnerability and abuse-check plan (proportional; no installs/paid)

No installations or paid services are authorized in H10.

- Base/lock review: record the pinned base digest and the exact 15-pin
  remote lock already verified in H9; registry metadata inspection is not a
  vulnerability assessment. Any scanner use needs separate owner
  authorization, named tool and version, and a recorded report; none is run
  by Muse in authoring this document.
- Abuse checks (after authorization, bounded, disposable config, stop at
  first unexpected result): confirm 401/403/404 fixed bodies carry no
  reflected input (§7); confirm oversize → 413, slow body → app 408 or a
  recorded proxy timeout, >30 evaluation attempts/min → 429, and 2-slot
  concurrency → 429 without cross-request leakage; confirm all
  application-generated responses carry `no-store` and record
  proxy-generated headers separately without assuming they match. Small
  counts only; no soak, flood, or distributed-load testing is authorized
  by this proposal.
- Representative competition load remains unverified under the proposed
  0.5 CPU / 256m limits.

## 7. External smoke-test expectations (app versus proxy responses)

Run only after all §9 gates pass, over HTTPS to the approved hostname.
Attribute each response using supporting evidence: app responses use the
fixed H8 bodies below; for any other shape (Traefik/Coolify page, empty
response, unexpected status), record its exact status, headers, and body
and attribute the producing layer only with supporting evidence, otherwise
mark it unknown. `no-store` expectations below apply to
application-generated responses only; record proxy-generated headers
separately and do not assume they match.

- Health: `GET /api/health` with allowed Host → `200
  {"status":"ok","synthetic_only":true}` with `Cache-Control: no-store`;
  no auth. Host-denial cases are covered in the Host row below.
- Canonical cases (complete synthetic opportunity; costs `$290.00` and
  surplus `$130.00` unchanged across all three; `profile_id:
  synthetic-box-001`, `model_invoked: false`, `no-store` on each):
  `$2.00` → `NEGOTIATE`, revenue `480.00`, gap `60.00`; `$1.75` → `ACCEPT`,
  revenue `420.00`, gap `0.00`; unknown (`null`) → `NEED_MORE_INFORMATION`,
  revenue/gap null.
- Auth: missing/wrong token → `401 {"detail":"Unauthorized"}` with
  `WWW-Authenticate: Bearer` and `no-store`; the header appears only on 401.
- Host: direct application Host test with wrong `Host` →
  `403 {"detail":"Forbidden"}`, fixed body, no reflection. Public routing
  test with an incorrect public Host may be rejected by Traefik before
  reaching the app; record the actual status, headers, and body and do not
  require the application's fixed 403 externally.
- Origin: any `Origin` header on evaluation → `403 {"detail":"Origin not
  allowed"}`.
- Disabled routes: `/docs`, `/redoc`, `/openapi.json`, `/`,
  `/api/v1/agent`, `/api/v1/freight/evaluate`, `/api/v1/browser/evaluate`
  (and any other non-allowlisted path) → `404 {"detail":"Not Found"}` with
  `no-store`; wrong methods → `405`.
- Body/rate limits: body over 32 KiB → app `413 {"detail":"Request body
  too large"}` unless the proxy rejects first (record which layer acted);
  slow body → app `408 {"detail":"Request timeout"}` or a recorded proxy
  timeout; >30/min → `429 {"detail":"Rate limit exceeded"}`; 2 concurrent
  slots full → `429 {"detail":"Too many concurrent evaluations"}`.
- TLS/redirect behavior per §3 is verified alongside these cases using
  plain-HTTP requests without credentials or sensitive bodies; record the
  actual behavior without assuming a redirect protects credentials already
  sent over HTTP.

## 8. Stop and rollback (future competition app only)

Applies only to `axle-meta-hackathon-api` after an approved deployment.

- Stop: stop (not remove) only the competition app through Coolify;
  stopping may leave an exited container. Verify no competition container
  remains running and application serving is unavailable: health no longer
  returns the application success response, and evaluation is unavailable.
  A proxy `502`/`503` or maintenance response is compatible with a stopped
  backend, not evidence the app is serving.
- Rollback: for this initial release, stopping the app is the rollback.
  Future rollback may restore a previously verified competition
  image/configuration. No shared code path is affected; local demo and
  production workloads are untouched.
- Never restart the shared proxy or change shared firewall/proxy settings
  as part of this procedure; the pending proxy changes stay unresolved.
- Credentials after stop: rotate per §2 if exposure is suspected;
  otherwise retain the secret-manager value for the next approved start.
  Stop immediately to suspend.

## 9. Approval gates (each explicit; no gate implies the next)

1. Publication: owner approves publishing branch
   `h10-coolify-preparation` for review.
2. Merge: owner approves merging H10 docs; reselect the final deployment
   SHA afterward.
3. Coolify resource creation: owner approves creating the dedicated
   competition project/environment and `axle-meta-hackathon-api` with the
   §0 values (manual deploys; no auto/preview).
4. Secrets: owner approves generating, storing, and injecting
   `AXLE_API_TOKEN` and the exact `AXLE_API_ALLOWED_HOSTS` as runtime-only
   env.
5. DNS: owner approves configuring `axle-meta.flyboxfly.com` and its
   propagation/verification.
6. Deployment and public exposure: owner approves the build from the
   reselected SHA, TLS/proxy/logging configuration, and public serving;
   before deployment, require reviewed configuration and available
   preflight evidence only. After separately authorized deployment,
   perform external smoke tests (§7). Failed tests require stopping the
   competition app. External deployment evidence cannot precede
   deployment.

## 10. Remaining deployment blockers

- All §9 approvals outstanding; no Coolify resource, secret, DNS record, or
  deployment exists.
- Final deployment SHA must be reselected after any approved H10 merge.
- Hostname neither approved nor configured; TLS/proxy/logging/timeout/body
  limit behavior unverified with no confirmed defaults.
- Installed-version support unverified for custom Docker options, restart
  policy, Dockerfile-check precedence, and app log-rotation provisioning.
- Build-context allowlist contents and honored ignore file unverified.
- Deployment-network egress controls unresolved; shared-proxy pending
  changes unexplained (do not restart the shared proxy).
- Vulnerability assessment and representative-load verification pending;
  no installs or paid services authorized.
