# H9 Deployment Packaging — Review Candidate (Not Deployed)

Status: review-only packaging proposal for the existing isolated synthetic
Axle API (`axle_hackathon.remote_app:app`). No deployment occurred, no
container image was built, and no Docker command in this document has been
executed. Owner-executed Mac evidence is recorded for §4A (full suite:
157 passed in 3.77s) and §4B (corrected 15-pin clean install, `pip check`,
and clean import); these are Mac results only, not GitHub CI or Linux
container validation. The owner runs all remaining validation below. Base
`e162542` per task brief; H8 behavior, canonical economics, and H1–H7
functionality are preserved (no application source changed).

See also: [H8 remote design](H8_REMOTE_DESIGN.md) for the enforced boundary
(auth, host allowlist, limits, error mapping, proxy assumptions).

## 1. Proposed file list

New files (six; no application source modified):

- `requirements.remote.lock.txt` — remote-runtime candidate lock (15 pins,
  exact versions grounded in `requirements.lock.txt`). Mac clean-environment
  verification passed (§4B); still a candidate pending Linux container
  verification; no hashes; Linux/container install not claimed.
- `Dockerfile.remote` — dedicated image for `remote_app:app`. Python 3.11+
  candidate base (unverified tag, no digest pinned), minimal COPY set,
  numeric non-root user, single Uvicorn worker, explicit flags, stdlib
  HEALTHCHECK. No baked-in tokens, keys, hostnames, or production config.
- `Dockerfile.remote.dockerignore` — Dockerfile-specific build-context
  allowlist (default-deny plus re-included packaging/runtime files only).
- `deploy/remote_healthcheck.py` — stdlib-only HEALTHCHECK probe: loopback
  TCP transport with an explicit runtime `Host` from `AXLE_API_ALLOWED_HOSTS`,
  bounded timeout, fail-closed on missing/empty/wildcard config.
- `tests/test_h9_packaging.py` — offline packaging validation: lock grounding,
  health-probe behavior, and a subprocess isolation test of the staged module
  closure with disposable config and raw ASGI calls. Explicitly does not cover
  container, install, or egress isolation.
- `docs/H9_DEPLOYMENT.md` — this document.

`README.md` gains only a short H9 pointer (no behavior or history changes).

## 2. Design choices

- **No app changes.** `remote_app.py`, `axle_api.py`, `schemas.py`, and
  `economics.py` are staged as-is. No packaging blocker was found, so no
  application source was modified.
- **Five-module closure.** The image copies only `__init__.py`,
  `remote_app.py`, `axle_api.py`, `schemas.py`, and `economics.py` — the
  complete import surface of the remote boundary. Excluded: `app.py`,
  `web.py`, `meta_agent.py`, `vision.py`, `external_agent.py`,
  `carrier.html`, tests, fixtures, browser assets, screenshots, docs.
- **Candidate lock, 15 pins.** FastAPI/Starlette/Pydantic serving plus
  Uvicorn and their transitive deps as recorded in `requirements.lock.txt`:
  annotated-doc, annotated-types, anyio, click, fastapi, h11, idna,
  opentelemetry-api, pydantic, pydantic_core, sniffio, starlette,
  typing-inspection, typing_extensions, uvicorn. fastapi==0.162.0 requires
  opentelemetry-api>=1.44.0 unconditionally; only the API package is pinned
  (==1.45.1), no SDK or exporter extras. Excluded: openai, httpx/httpx2,
  httpcore/httpcore2, Pillow, pytest (and its deps), socksio, jiter, certifi,
  truststore. Package-installation status (distinct from the loaded-module
  check): Mac clean-install verification of the corrected 15-pin lock
  passed (§4B); Linux/container install remains pending.
- **Unverified base tag, no digest.** `FROM python:3.11.14-slim-bookworm` is
  a specific 3.11+ candidate (3.11+ required for `asyncio.timeout`). Tag
  availability is unverified and no digest is pinned; the owner must confirm
  the tag and pin a verified digest before any deployment.
- **Numeric non-root.** Dedicated UID/GID 65532; `USER 65532`; staged app
  files and the health probe are root-owned (`--chown=0:0`) and readable /
  executable as needed, so the runtime process does not own its application
  source. No root runtime process.
- **Uvicorn flags.** Exactly `--workers 1` (H8 limiter is per-process), no
  `--reload`, `--lifespan on` (fail-closed startup validation),
  `--no-proxy-headers` (proxy-header processing explicitly disabled; the app
  ignores `X-Forwarded-*`), `--no-access-log` (access log disabled).
  Remaining risks documented in the Dockerfile: Uvicorn error/startup logs
  may still carry tracebacks, and the platform proxy may log access metadata.
  Verify proxy log settings and retention before deployment.
- **HEALTHCHECK without baked config.** The probe reads the runtime
  `AXLE_API_ALLOWED_HOSTS` inside the container and sends its first entry as
  the `Host` header over loopback TCP (transport only, not an allowlist
  bypass). The probe 5 s timeout is a per-socket-operation timeout, not a
  total deadline; Docker `HEALTHCHECK --timeout=5s` supplies the overall
  process timeout. No localhost default, no wildcard; misconfiguration fails
  closed.
- **Default-deny context.** The `.dockerignore` excludes everything (`**`)
  then re-includes only the Dockerfile, remote lock, health probe, and five
  modules (with parent dirs). Secrets, `.git`, venvs, tests, fixtures,
  screenshots, docs, and the full lock never enter the build context.
  Per-Dockerfile ignore-file support depends on the builder (BuildKit
  honors `Dockerfile.remote.dockerignore` for `-f Dockerfile.remote`);
  the owner must confirm which file the platform builder uses.
- **Tests prove behavior, not text.** `tests/test_h9_packaging.py` checks
  lock grounding, probe behavior, and staged-closure behavior in an isolated
  subprocess; it deliberately does not assert Dockerfile flag strings.

## 3. What this package does not claim

- No container was built, run, or inspected; all container steps are pending.
- History: owner Mac clean install of the prior 14-pin candidate succeeded
  (install and `pip check` passed, selecting opentelemetry-api==1.45.1
  transitively); it revealed the missing explicit pin. Superseded by §4B:
  owner Mac clean install of the corrected 15-pin lock succeeded — install
  passed, `pip check` reported “No broken requirements found”, and the
  installed set exactly matched all 15 pins. That is a package-installation
  result, distinct from the loaded-module check (§4B). Linux/container
  install remains pending.
- Offline tests do not establish container contents, install success, or
  network-egress isolation (stated in the test module docstring).
- No public hostname is chosen and no credentials exist. Placeholders below
  (`<pending-owner-hostname>`, `<reviewer-token>`) are not real values.
- Baseten is not integrated; the working Meta integration is unchanged.

## 4. Owner-run validation commands

Run in order. Stop at the first failure. `<pending-owner-hostname>` is a
placeholder for the future dedicated hostname (no real host chosen);
`<reviewer-token>` is a placeholder for a generated token (generate per
H8 design §Reviewer-token provisioning; never commit or paste it).

### A. Offline checks (no container runtime needed)

Prerequisite: an existing activated `.venv` with dependencies already
installed. Do not recreate the venv or reinstall dependencies for these
checks. From the workspace root on branch `h9-deployment-package`:

```sh
. .venv/bin/activate
python -m pytest tests/test_h9_packaging.py -q
python -m pytest -q
```

Observed (owner-executed, Mac, this branch): H9 file passes and the full
suite passes — 157 passed in 3.77s with no failures. Prior baseline per
task brief was 145 tests passed on base `e162542`. Mac result only; not
GitHub CI or Linux container validation.

### B. Clean dependency installation (candidate-lock verification)

History: owner Mac clean install of the prior 14-pin candidate succeeded
and `pip check` passed, selecting opentelemetry-api==1.45.1 transitively
via fastapi==0.162.0 and revealing the missing explicit pin.

Owner-executed evidence (Mac, corrected 15-pin lock), from the procedure
below in a fresh virtual environment with the remote lock only:

- Package-installation checks (what is installed; distinct from which
  modules are loaded at import): install succeeded; `pip check` reported
  “No broken requirements found”; the installed runtime exactly matched
  all 15 pins.
- Loaded-module check (what the import loads; distinct from package
  installation): the remote application imported successfully using that
  minimal environment, and openai, httpx, PIL, and pytest were absent
  from loaded modules.

Mac results only; not GitHub CI or Linux container validation.

Fresh environment, remote lock only — proves the candidate lock installs
and the staged boundary imports without the full project set.
Actually executed (owner Mac): fresh venv creation, `pip install` of the
remote lock only, `pip check`, and `pip list`. The `pip show` line below
is illustrative only and was not executed:

```sh
CLEAN=$(mktemp -d)
python3 -m venv "$CLEAN/venv"
"$CLEAN/venv/bin/pip" install -r requirements.remote.lock.txt
"$CLEAN/venv/bin/pip" check
"$CLEAN/venv/bin/pip" list
# Illustrative only, not executed:
# "$CLEAN/venv/bin/pip" show openai httpx Pillow pytest
```

Observed (owner Mac, corrected 15-pin lock) — package-installation
checks only, not a loaded-module check: install succeeded; `pip check`
reported “No broken requirements found”; `pip list` showed the remote
closure exactly matching all 15 pins (plus pip/setuptools). No `pip show`
was executed; openai/httpx/Pillow/pytest absence follows from the verified
exact 15-pin installed inventory, which contains none of them.

Then confirm the boundary imports under the clean interpreter (disposable
config, no server started). This proves import success and checks loaded
modules only; it is not canonical serving or startup validation.
The script below is a reusable verification example, not an exact
transcript of the owner-executed command. The observed import result and
loaded-module checks are recorded below; the constant assertions are
additional suggested checks.

```sh
cd $HOME/Downloads/axle-hackathon-working
PYTHONPATH=src AXLE_API_TOKEN=h9-clean-disposable-token \
  AXLE_API_ALLOWED_HOSTS=h9-clean.test \
  "$CLEAN/venv/bin/python" - <<'EOF'
import sys
import axle_hackathon.remote_app as ra
tops = {m.split('.')[0].lower() for m in sys.modules}
assert not (tops & {'openai', 'httpx', 'pil', 'pytest'}), tops
assert ra.MAX_BODY_BYTES == 32768 and ra.BODY_READ_TIMEOUT_SECONDS == 10.0
print('PASS: remote application imports with minimal dependencies.')
EOF
```

Observed (owner Mac, corrected 15-pin lock) — loaded-module check only,
distinct from package installation: printed
`PASS: remote application imports with minimal dependencies.` with no
assertion error; openai, httpx, PIL, and pytest were absent from loaded
modules. Mac result only; not GitHub CI or Linux container validation.
This still does not verify canonical serving, startup validation, the
container image (§4C), Linux Python 3.11 compatibility, or egress (§4D).

### C. Pending container checks (require a container runtime)

None of these commands have been executed; all commands in §4C and §4D
are illustrative only. They require Docker (or an equivalent) and a verified
base-tag digest (§2). Replace the `FROM` line with the verified pin before
building. Docker, Podman, and Colima were not found on the owner Mac PATH;
install and confirm a runtime before starting.

Build (from the workspace root):

```sh
docker build -f Dockerfile.remote -t axle-remote:h9 .
```

Run with runtime-only config (publish to loopback for local checks only;
generate a fresh disposable token for these checks, not a reviewer token):

```sh
docker run -d --name axle-h9 \
  -e AXLE_API_TOKEN='<disposable-local-token>' \
  -e AXLE_API_ALLOWED_HOSTS='h9-local.test' \
  -p 127.0.0.1:8000:8000 axle-remote:h9
docker ps --filter name=axle-h9
```

1. **Non-root identity** — expect `uid=65532`:

   ```sh
   docker exec axle-h9 id
   docker inspect axle-h9 --format '{{.Config.User}}'
   ```

2. **Runtime contents** — expect exactly the five modules plus the probe,
   and no local-only packages:

   ```sh
   docker exec axle-h9 ls -la /app/src/axle_hackathon /app/deploy
   docker exec axle-h9 pip list
   docker exec axle-h9 pip check
   docker exec axle-h9 pip show openai httpx Pillow pytest
   docker exec axle-h9 python -c "import axle_hackathon.app"  # expect ModuleNotFoundError
   ```

3. **Health** — explicit allowed `Host`, expect `{"status":"ok",
   "synthetic_only":true}` and `cache-control: no-store`:

   ```sh
   curl -si -H 'Host: h9-local.test' http://127.0.0.1:8000/api/health
   docker inspect axle-h9 --format '{{.State.Health.Status}}'
   ```

4. **Authentication rejection** — missing/wrong token, expect 401 with
   `WWW-Authenticate: Bearer` and `no-store`:

   ```sh
   curl -si -H 'Host: h9-local.test' -H 'Content-Type: application/json' \
     -d '{}' http://127.0.0.1:8000/api/v1/axle/evaluate
   ```

5. **Host/Origin rejection** — expect 403 fixed bodies, no reflection:

   ```sh
   curl -si -H 'Host: other.test' -H 'Authorization: Bearer <disposable-local-token>' \
     -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8000/api/v1/axle/evaluate
   curl -si -H 'Host: h9-local.test' -H 'Authorization: Bearer <disposable-local-token>' \
     -H 'Content-Type: application/json' -H 'Origin: https://h9-local.test' \
     -d '{}' http://127.0.0.1:8000/api/v1/axle/evaluate
   ```

6. **Disabled routes** — each expect 404 `{"detail":"Not Found"}`:

   ```sh
   for p in /docs /redoc /openapi.json / /api/v1/agent /api/v1/freight/evaluate /api/v1/browser/evaluate; do
     curl -s -o /dev/null -w "$p %{http_code}\n" -H 'Host: h9-local.test' "http://127.0.0.1:8000$p"
   done
   ```

7. **Canonical results** — three evaluations over the complete synthetic
   case; expect NEGOTIATE / ACCEPT / NEED_MORE_INFORMATION with gaps
   `60.00` / `0.00` / null and unchanged `$290.00` costs / `$130.00`
   surplus. Save the body to a file per target (example for `$2.00`):

   ```sh
   cat > /tmp/h9-eval.json <<'EOF'
   {"opportunity": {"equipment": "box_truck_26ft", "payout": "420",
     "loaded_miles": "180", "deadhead_miles": "60", "diesel_per_gallon": "4",
     "mpg": "10", "tolls": "20", "driver_cost": "80",
     "maintenance_per_mile": "0.10", "equipment_trip_cost": "50",
     "insurance_trip_allocation": "20", "operating_hours": "6",
     "schedule_feasible": true},
    "benchmark": {"target_all_mile_rpm": "2.00", "confirmed": true},
    "facts_confirmed": true, "source": "screenshot"}
   EOF
   curl -s -H 'Host: h9-local.test' -H 'Authorization: Bearer <disposable-local-token>' \
     -H 'Content-Type: application/json' --data @/tmp/h9-eval.json \
     http://127.0.0.1:8000/api/v1/axle/evaluate
   ```

   Repeat with `"1.75"` and `null` targets; compare decisions, gaps, costs,
   `profile_id: synthetic-box-001`, `model_invoked: false`, and
   `cache-control: no-store` on each response.

8. **Shutdown** — stop, verify the endpoint is down, remove:

   ```sh
   docker stop axle-h9
   curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: h9-local.test' http://127.0.0.1:8000/api/health || echo 'endpoint down (expected)'
   docker rm axle-h9
   docker ps -a --filter name=axle-h9
   ```

### D. Optional network-none container test (exec + loopback only)

Purpose: prove the staged app serves health/evaluation with no container
egress path, using in-container exec over loopback. This is NOT deployment
egress policy and NOT external proxy connectivity: production still needs a
proxy in front (TLS, Host preservation, timeouts) and a platform-level
deny-by-default egress rule, neither of which this test configures or
verifies.

```sh
docker run -d --name axle-h9-nonone --network=none \
  -e AXLE_API_TOKEN='<disposable-local-token>' \
  -e AXLE_API_ALLOWED_HOSTS='h9-local.test' axle-remote:h9
docker exec axle-h9-nonone python /app/deploy/remote_healthcheck.py && echo 'in-container health ok'
docker exec -i axle-h9-nonone python - <<'EOF'
import http.client, json, os
token = os.environ['AXLE_API_TOKEN']
c = http.client.HTTPConnection('127.0.0.1', 8000, timeout=5)
c.request('GET', '/api/health', headers={'Host': 'h9-local.test'})
r = c.getresponse()
assert r.status == 200, r.status
assert json.loads(r.read()) == {'status': 'ok', 'synthetic_only': True}
print('loopback health ok')
payload = {"opportunity": {"equipment": "box_truck_26ft", "payout": "420",
    "loaded_miles": "180", "deadhead_miles": "60", "diesel_per_gallon": "4",
    "mpg": "10", "tolls": "20", "driver_cost": "80",
    "maintenance_per_mile": "0.10", "equipment_trip_cost": "50",
    "insurance_trip_allocation": "20", "operating_hours": "6",
    "schedule_feasible": True},
  "benchmark": {"target_all_mile_rpm": "2.00", "confirmed": True},
  "facts_confirmed": True, "source": "screenshot"}
c2 = http.client.HTTPConnection('127.0.0.1', 8000, timeout=5)
c2.request('POST', '/api/v1/axle/evaluate', body=json.dumps(payload),
  headers={'Host': 'h9-local.test', 'Authorization': 'Bearer ' + token,
    'Content-Type': 'application/json'})
r2 = c2.getresponse()
assert r2.status == 200, r2.status
ev = json.loads(r2.read())['evaluation']
assert ev['decision'] == 'NEGOTIATE', ev
assert ev['revenue_gap_to_target'] == '60.00', ev
assert ev['estimated_operating_cost'] == '290.00', ev
assert ev['estimated_operating_surplus_after_allocated_costs'] == '130.00', ev
print('loopback evaluate ok')
EOF
docker stop axle-h9-nonone && docker rm axle-h9-nonone
```

Expected: the health probe, loopback health, and authenticated canonical
evaluation all succeed with `--network=none`. A pass here does not approve
deployment networking; see §5 egress row.

## 5. Proposed Coolify configuration (all unresolved until approved)

No public hostname is chosen and no credentials are provisioned. Every row
needs explicit owner approval with concrete values before any deployment.
`<pending-owner-hostname>` and `<reviewer-token>` are placeholders, not
decisions.

| Setting | Proposed value | Status |
|---|---|---|
| Service | Dedicated new service for the remote boundary only; separate from local demo and production workloads | Proposed, unresolved |
| Source | Branch `h9-deployment-package`, Dockerfile `Dockerfile.remote` | Proposed, unresolved |
| Public hostname | `<pending-owner-hostname>` (no host chosen) | Unresolved |
| Internal port | 8000 (container EXPOSE; proxy forwards to it) | Proposed, unresolved |
| Workers / replicas | One Uvicorn worker (`--workers 1` in image) and exactly one container replica (H8 limiter is per-process) | Proposed, unresolved |
| `AXLE_API_TOKEN` | Runtime-only secret `<reviewer-token>` injected at start; never baked into the image | Unresolved (no token issued) |
| `AXLE_API_ALLOWED_HOSTS` | Runtime-only `<pending-owner-hostname>` exactly (lowercase); no localhost/testserver entries | Unresolved |
| Health check | Container HEALTHCHECK (`deploy/remote_healthcheck.py`, explicit Host from runtime allowlist); platform may add an HTTPS health probe against `<pending-owner-hostname>/api/health` | Proposed, unresolved |
| TLS | Terminate at the platform proxy; HTTPS-only to clients, HTTP rejected or redirected; HSTS and cert management at the proxy | Unresolved |
| Proxy Host handling | Preserve original `Host` unchanged to the app (allowlist matches what the app sees); do not strip `Authorization` or `Origin` | Proposed, unresolved |
| Proxy timeouts | Connection/header/body timeouts at the proxy in front of the app 10 s body deadline; exact values unset | Unresolved |
| Proxy body limits | At or below the app 32 KiB limit; exact value unset | Unresolved |
| Logging | App emits no request logs; Uvicorn access log disabled. Proxy/app error-log capture, redaction, retention, and alerting unset — verify no bodies, tokens, or facts are recorded | Unresolved |
| Resource limits | CPU/memory limits and request concurrency caps unset | Unresolved |
| Restart behavior | Restart policy unset; note limiter state is in-memory and resets on restart | Unresolved |
| Network egress | Deny-by-default outbound at the platform; no allowlist defined; the app needs no outbound for evaluation | Unresolved |

## 6. Stop / rollback procedure

Deployment has not occurred; this procedure applies only to a future
approved deployment.

- **Stop:** stop the dedicated remote service through Coolify (or
  `docker stop` for local checks). Verify no remote container remains
  (`docker ps`), health no longer returns the application success response,
  and evaluation is unavailable. Leave production workloads untouched.
- **Proxy behavior while stopped:** a running reverse proxy in front of a
  stopped backend may return `502`/`503` or a maintenance page. A proxy
  error response is compatible with a stopped backend, not evidence the app
  is serving.
- **Rollback:** stopping the remote service is the rollback. The local demo
  app is a separate entrypoint and is unaffected; no shared code changed.
- **Credentials after stop:** if the stop was due to suspected exposure,
  rotate the reviewer token per H8 design (new value, restart all
  instances); otherwise retain the secret-manager value for the next
  approved start. To suspend immediately, stop the service.

## 7. Approval boundary (explicit)

No publication, reviewer access, or deployment is approved by this
candidate. Before any exposure beyond loopback, the owner must explicitly
approve: the verified base-image digest, the dedicated public hostname, TLS
and proxy configuration (Host preservation, timeouts, body limits,
logging), resource limits, restart policy, egress deny-by-default with
evidence, reviewer-token issuance/rotation, and the §4A–§4C evidence for
this exact branch. H8 lists the remaining required controls; none are
closed by this packaging slice.

## 8. Unverified assumptions and remaining requirements

- Base tag `python:3.11.14-slim-bookworm` availability and digest: unverified.
- Which ignore file the platform builder honors
  (`Dockerfile.remote.dockerignore` vs root `.dockerignore`): unverified.
- Corrected `requirements.remote.lock.txt` (15 pins): Mac clean install,
  `pip check` (“No broken requirements found”), exact 15-pin installed-set
  match (package-installation checks), and clean import with openai, httpx,
  PIL, and pytest absent from loaded modules (loaded-module check):
  verified on Mac (§4B). History: owner Mac clean install of the 14-pin
  candidate succeeded and `pip check` passed, selecting
  opentelemetry-api==1.45.1 transitively and revealing the missing
  explicit pin. Linux/container install, base-tag availability/digest,
  and Linux Python 3.11 compatibility: pending.
- All container checks (§4C) and the optional network-none probe (§4D):
  pending; Docker, Podman, and Colima were not found on the owner Mac PATH.
- Every Coolify row in §5: unresolved; no hostname, token, TLS, proxy,
  logging, limits, restart, or egress decisions made.
- H8 remaining controls (WAF, audit logging, abuse defense beyond one
  process, load/soak testing, security review): still required.
