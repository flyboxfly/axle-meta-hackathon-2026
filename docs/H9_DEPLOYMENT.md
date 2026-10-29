# H9 Deployment Packaging — Review Candidate (Not Publicly Deployed)

Status: review-only packaging proposal for the existing isolated synthetic
Axle API (`axle_hackathon.remote_app:app`). No public deployment occurred
and no external client/proxy connectivity was tested. Owner-executed VPS
container validation was completed on October 29, 2026, using source commit
`dcc56cf028548289ac367b32a4e606a1d56b47da` on an x86_64 VPS (Docker 29.8.1,
Buildx v0.37.1): linux/amd64 image `axle-h9-validation:dcc56cf` built
successfully from the pinned Python base; build-time dependency installation
and `pip check` passed; a hardened network-none test container ran, was
inspected, probed, and removed as recorded in §4C–§4D. Owner-executed Mac
evidence is recorded for §4A (full suite: 157 passed in 3.77s) and §4B
(corrected 15-pin clean install, `pip check`, and clean import); these are
Mac results only, not GitHub CI. Base `e162542` per task brief; H8 behavior,
canonical economics, and H1–H7 functionality are preserved (no application
source changed). The validation image and temporary VPS source workspace
remain; container cleanup removed only the test container, not the image or
workspace.

See also: [H8 remote design](H8_REMOTE_DESIGN.md) for the enforced boundary
(auth, host allowlist, limits, error mapping, proxy assumptions).

## 1. Proposed file list

New files (six; no application source modified):

- `requirements.remote.lock.txt` — remote-runtime lock (15 pins, exact
  versions grounded in `requirements.lock.txt`). Mac clean-environment
  verification passed (§4B); Linux container install verified on the VPS on
  October 29, 2026 (§4C): build-time install and `pip check` passed, and the
  installed runtime exactly matched all 15 pins excluding packaging tools.
  No hashes.
- `Dockerfile.remote` — dedicated image for `remote_app:app`. Python 3.11+
  base pinned to the owner-observed index digest
  (`python:3.11.14-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d`;
  tag existence and linux/amd64 availability confirmed via owner registry
  query from the x86_64 VPS on October 29, 2026; linux/amd64 image
  `axle-h9-validation:dcc56cf` successfully built from this base on the same
  VPS, §4C), minimal COPY set, numeric non-root user, single Uvicorn worker,
  explicit flags, stdlib HEALTHCHECK. No baked-in tokens, keys, hostnames,
  or production config.
- `Dockerfile.remote.dockerignore` — Dockerfile-specific build-context
  allowlist (default-deny plus re-included packaging/runtime files only).
  Complete build-context allowlist verification remains pending: a small
  transferred context alone does not prove its exact contents.
- `deploy/remote_healthcheck.py` — stdlib-only HEALTHCHECK probe: loopback
  TCP transport with an explicit runtime `Host` from `AXLE_API_ALLOWED_HOSTS`,
  bounded timeout, fail-closed on missing/empty/wildcard config.
  Container-local probe passed on the VPS (§4C–§4D).
- `tests/test_h9_packaging.py` — offline packaging validation: lock grounding,
  health-probe behavior, and a subprocess isolation test of the staged module
  closure with disposable config and raw ASGI calls. Explicitly does not cover
  container, install, or egress isolation. Container contents, install, and
  loopback serving were verified separately by owner-executed VPS checks
  (§4C–§4D); deployment-network egress remains pending.
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
  VPS in-container check confirmed exactly five application modules (§4C).
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
  passed (§4B); Linux container install verified on the VPS on October 29,
  2026 (§4C): build-time install and `pip check` passed, and the installed
  runtime exactly matched all 15 pins excluding packaging tools.
- **Pinned base image (observed index digest).**
  `FROM python:3.11.14-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d`
  (3.11+ required for `asyncio.timeout`). The owner queried the registry
  from the x86_64 VPS on October 29, 2026; tag existence and linux/amd64
  availability were confirmed (linux/amd64 manifest digest observed:
  `sha256:83f339c1be6340ae1096010fdccf6552ac932d8f410d45d206014916bdf37e48`).
  The base is pinned to the observed multi-platform OCI index digest above.
  The linux/amd64 image was built successfully on the x86_64 VPS on October
  29, 2026 (`axle-h9-validation:dcc56cf`); Linux dependency compatibility
  and container execution verified (§4C–§4D). Image vulnerability assessment
  remains pending. Registry metadata inspection is not an image
  vulnerability assessment.
- **Numeric non-root.** Dedicated UID/GID 65532; `USER 65532`; staged app
  files and the health probe are root-owned (`--chown=0:0`) and readable /
  executable as needed, so the runtime process does not own its application
  source. No root runtime process. VPS inspection confirmed `User=65532` and
  `id` confirmed UID/GID 65532; checked source/probe files were root-owned
  and non-writable (§4C).
- **Uvicorn flags.** Exactly `--workers 1` (H8 limiter is per-process), no
  `--reload`, `--lifespan on` (fail-closed startup validation),
  `--no-proxy-headers` (proxy-header processing explicitly disabled; the app
  ignores `X-Forwarded-*`), `--no-access-log` (access log disabled).
  Remaining risks documented in the Dockerfile: Uvicorn error/startup logs
  may still carry tracebacks, and the platform proxy may log access metadata.
  Verify proxy log settings and retention before deployment. Infrastructure
  logging review remains pending.
- **HEALTHCHECK without baked config.** The probe reads the runtime
  `AXLE_API_ALLOWED_HOSTS` inside the container and sends its first entry as
  the `Host` header over loopback TCP (transport only, not an allowlist
  bypass). The probe 5 s timeout is a per-socket-operation timeout, not a
  total deadline; Docker `HEALTHCHECK --timeout=5s` supplies the overall
  process timeout. No localhost default, no wildcard; misconfiguration fails
  closed. The VPS container reported healthy and the container-local probe
  passed (§4C–§4D).
- **Default-deny context.** The `.dockerignore` excludes everything (`**`)
  then re-includes only the Dockerfile, remote lock, health probe, and five
  modules (with parent dirs). Secrets, `.git`, venvs, tests, fixtures,
  screenshots, docs, and the full lock never enter the build context.
  Per-Dockerfile ignore-file support depends on the builder (BuildKit
  honors `Dockerfile.remote.dockerignore` for `-f Dockerfile.remote`);
  the owner must confirm which file the platform builder uses. Complete
  build-context allowlist verification remains pending: a small transferred
  context alone does not prove its exact contents.
- **Tests prove behavior, not text.** `tests/test_h9_packaging.py` checks
  lock grounding, probe behavior, and staged-closure behavior in an isolated
  subprocess; it deliberately does not assert Dockerfile flag strings.

## 3. What this package does not claim

- No public deployment occurred; no external client/proxy connectivity was
  tested. VPS validation used exec plus loopback only with `--network=none`,
  no published ports, and no host mounts; it does not establish public
  serving.
- History: owner Mac clean install of the prior 14-pin candidate succeeded
  (install and `pip check` passed, selecting opentelemetry-api==1.45.1
  transitively); it revealed the missing explicit pin. Superseded by §4B:
  owner Mac clean install of the corrected 15-pin lock succeeded — install
  passed, `pip check` reported “No broken requirements found”, and the
  installed set exactly matched all 15 pins. That is a package-installation
  result, distinct from the loaded-module check (§4B). Linux/container
  install since verified on the VPS on October 29, 2026 (§4C): build-time
  install and `pip check` passed, the installed runtime exactly matched all
  15 pins excluding packaging tools, and the in-container loaded-module check
  passed (openai, httpx, PIL, and pytest absent).
- Offline tests do not establish container contents, install success, or
  network-egress isolation (stated in the test module docstring). Container
  contents, install, and loopback serving were established separately by the
  VPS checks (§4C–§4D); deployment-network egress isolation remains pending.
- No public hostname is chosen and no credentials exist. Placeholders below
  (`<pending-owner-hostname>`, `<reviewer-token>`) are not real values.
- Baseten is not integrated; the working Meta integration is unchanged.
- Still pending: TLS, proxy timeouts/body limits, and infrastructure logging
  review; deployment-network egress controls; vulnerability assessment and
  broader load/abuse testing; complete build-context allowlist verification
  (a small transferred context alone does not prove its exact contents).
- The validation image (`axle-h9-validation:dcc56cf`) and temporary VPS
  source workspace remain; container cleanup removed only the test container,
  not the image or workspace.

## 4. Owner-run validation commands

Run in order. Stop at the first failure. `<pending-owner-hostname>` is a
placeholder for the future dedicated hostname (no real host chosen);
`<reviewer-token>` is a placeholder for a generated token (generate per
H8 design §Reviewer-token provisioning; never commit or paste it).

Executed evidence versus illustrative commands: §4A–§4B record Mac
owner-executed evidence. §4C–§4D record VPS owner-executed evidence from
October 29, 2026 (source commit
`dcc56cf028548289ac367b32a4e606a1d56b47da`, image
`axle-h9-validation:dcc56cf`) under “Observed (owner-executed, VPS)” notes.
Shell blocks in §4C–§4D are illustrative examples of the same checks, not
exact transcripts, unless stated. Docker warned `--time` is deprecated; future
examples use `docker stop --timeout`, not `--time`.

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

Mac results only; not GitHub CI. Linux/container install and Linux Python
3.11 compatibility were since verified on the VPS (§4C–§4D).

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
modules. Mac result only; not GitHub CI. Successful startup and canonical serving were verified separately in
the VPS container (§4C–§4D). Docker inspection confirmed Network=none;
loopback requests succeeded. No outbound connection attempt was tested,
and deployment-network egress controls remain pending.

### C. Container checks (owner-executed on the VPS, October 29, 2026)

Executed on the x86_64 VPS (Docker 29.8.1, Buildx v0.37.1) from source
commit `dcc56cf028548289ac367b32a4e606a1d56b47da`. The linux/amd64 image
`axle-h9-validation:dcc56cf` built successfully from the pinned Python base;
build-time dependency installation and `pip check` passed. The test container
ran with `--network=none`, a read-only filesystem, all capabilities dropped,
no-new-privileges, 256 MiB memory, 0.5 CPU, PID limit 64, restart disabled,
no published ports, no host mounts, and disposable synthetic configuration.
Commands below are illustrative examples of the same checks, not exact
transcripts. Docker, Podman, and Colima were not found on the owner Mac PATH;
no Mac runtime installation was required.

Build (from the workspace root; illustrative — the executed build produced
`axle-h9-validation:dcc56cf` for linux/amd64):

```sh
docker build -f Dockerfile.remote -t axle-remote:h9 .
```

Run with runtime-only config. Illustrative published-port form only (not
executed as written — the executed validation used `--network=none` with no
published ports and exec plus loopback only; generate a fresh disposable
token for these checks, not a reviewer token):

```sh
docker run -d --name axle-h9 \
  -e AXLE_API_TOKEN='<disposable-local-token>' \
  -e AXLE_API_ALLOWED_HOSTS='h9-local.test' \
  -p 127.0.0.1:8000:8000 axle-remote:h9
docker ps --filter name=axle-h9
```

Observed (owner-executed, VPS): the executed test container ran with network
none, read-only filesystem, all capabilities dropped, no-new-privileges,
256 MiB memory, 0.5 CPU, PID limit 64, restart disabled, no published ports,
no host mounts, and disposable synthetic configuration.

1. **Non-root identity** — expect `uid=65532`:

   ```sh
   docker exec axle-h9 id
   docker inspect axle-h9 --format '{{.Config.User}}'
   ```

   Observed (owner-executed, VPS): inspect showed the container running with
   `User=65532`, `Network=none`, and `ReadOnly=true`; `id` confirmed UID/GID
   65532.

2. **Runtime contents** — expect exactly the five modules plus the probe,
   and no local-only packages:

   ```sh
   docker exec axle-h9 ls -la /app/src/axle_hackathon /app/deploy
   docker exec axle-h9 pip list
   docker exec axle-h9 pip check
   docker exec axle-h9 pip show openai httpx Pillow pytest
   docker exec axle-h9 python -c "import axle_hackathon.app"  # expect ModuleNotFoundError
   ```

   Observed (owner-executed, VPS): in-container assertions passed — Linux
   Python 3.11; exactly five application modules; checked source/probe files
   root-owned and non-writable; installed runtime exactly matched all 15 pins
   excluding packaging tools; remote import did not load openai, httpx, PIL,
   or pytest.

3. **Health** — explicit allowed `Host`, expect `{"status":"ok",
   "synthetic_only":true}`:

   ```sh
   curl -si -H 'Host: h9-local.test' http://127.0.0.1:8000/api/health
   docker inspect axle-h9 --format '{{.State.Health.Status}}'
   ```

   Observed (owner-executed, VPS): the container was running and healthy; the
   container-local health probe passed. Published-port `curl` lines above
   are illustrative only; executed checks used in-container loopback via exec
   (see §4D).

4. **Authentication rejection** — missing/wrong token, expect 401 with
   `WWW-Authenticate: Bearer` and `no-store`:

   ```sh
   curl -si -H 'Host: h9-local.test' -H 'Content-Type: application/json' \
     -d '{}' http://127.0.0.1:8000/api/v1/axle/evaluate
   ```

   Observed (owner-executed, VPS): missing/wrong token returned 401 over
   in-container loopback. Illustrative host `curl` only; executed checks used
   exec plus loopback.

5. **Host/Origin rejection** — expect 403 fixed bodies, no reflection:

   ```sh
   curl -si -H 'Host: other.test' -H 'Authorization: Bearer <disposable-local-token>' \
     -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8000/api/v1/axle/evaluate
   curl -si -H 'Host: h9-local.test' -H 'Authorization: Bearer <disposable-local-token>' \
     -H 'Content-Type: application/json' -H 'Origin: https://h9-local.test' \
     -d '{}' http://127.0.0.1:8000/api/v1/axle/evaluate
   ```

   Observed (owner-executed, VPS): disallowed Host and Origin returned 403
   over in-container loopback. Illustrative host `curl` only; executed checks
   used exec plus loopback.

6. **Disabled routes** — each expect 404 `{"detail":"Not Found"}`:

   ```sh
   for p in /docs /redoc /openapi.json / /api/v1/agent /api/v1/freight/evaluate /api/v1/browser/evaluate; do
     curl -s -o /dev/null -w "$p %{http_code}\n" -H 'Host: h9-local.test' "http://127.0.0.1:8000$p"
   done
   ```

   Observed (owner-executed, VPS): tested disabled paths returned GET 404
   over in-container loopback. Illustrative host loop only; executed checks
   used exec plus loopback.

7. **Canonical results** — three evaluations over the complete synthetic
   case; expect NEGOTIATE / ACCEPT / NEED_MORE_INFORMATION with gaps
   `60.00` / `0.00` / null and unchanged `$290.00` costs / `$130.00`
   surplus. Save the body to a file per target (example for `$2.00`;
   illustrative host form — executed checks used in-container loopback):

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

   Observed (owner-executed, VPS): actual loopback HTTP tests passed —
   target 2.00 → NEGOTIATE, revenue 480.00, gap 60.00; target 1.75 → ACCEPT,
   revenue 420.00, gap 0.00; unknown target → NEED_MORE_INFORMATION,
   revenue/gap null. Costs remained 290.00; surplus 130.00; loaded RPM 2.33,
   all-mile RPM 1.75. Tested responses carried `Cache-Control: no-store`.

8. **Shutdown** — stop, verify the endpoint is down, remove (illustrative;
   use `--timeout`, not deprecated `--time`):

   ```sh
   docker stop --timeout 10 axle-h9
   curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: h9-local.test' http://127.0.0.1:8000/api/health || echo 'endpoint down (expected)'
   docker rm axle-h9
   docker ps -a --filter name=axle-h9
   ```

   Observed (owner-executed, VPS): the test container stopped with
   `ExitCode=0`, was removed, and the exact-name container listing was empty.
   The validation image and temporary VPS source workspace remain; cleanup
   did not remove them.

### D. Network-none container test (owner-executed on the VPS, October 29, 2026)

Purpose: prove the staged app serves health/evaluation with no container
egress path, using in-container exec over loopback. This is NOT deployment
egress policy and NOT external proxy connectivity: production still needs a
proxy in front (TLS, Host preservation, timeouts) and a platform-level
deny-by-default egress rule, neither of which this test configures or
verifies.

Observed (owner-executed, VPS): executed with `--network=none`, read-only
filesystem, all capabilities dropped, no-new-privileges, 256 MiB memory,
0.5 CPU, PID limit 64, restart disabled, no published ports, no host mounts,
and disposable synthetic configuration. The container-local health probe
passed, loopback health passed, and authenticated canonical loopback
evaluations passed (NEGOTIATE / ACCEPT / NEED_MORE_INFORMATION with the
economics recorded in §4C item 7, including 401/403/404 and `no-store`
behavior). Illustrative example below shows the same shape; it is not an
exact transcript.

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
docker stop --timeout 10 axle-h9-nonone && docker rm axle-h9-nonone
```

Expected: the health probe, loopback health, and authenticated canonical
evaluation all succeed with `--network=none`. Observed (owner-executed, VPS):
they did, under the hardened constraints above. A pass here does not approve
deployment networking; see §5 egress row. Deployment-network egress controls
remain pending.

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

Public deployment has not occurred; this procedure applies only to a future
approved deployment. The VPS validation container was already stopped
(`ExitCode=0`) and removed; the validation image and temporary VPS source
workspace remain.

- **Stop:** stop the dedicated remote service through Coolify (or
  `docker stop --timeout 10` for local checks; `--time` is deprecated).
  Verify no remote container remains (`docker ps`), health no longer returns
  the application success response, and evaluation is unavailable. Leave
  production workloads untouched.
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
candidate. VPS evidence now covers, for source commit
`dcc56cf028548289ac367b32a4e606a1d56b47da` (image
`axle-h9-validation:dcc56cf`, linux/amd64): the pinned base-image digest,
image build, Linux dependency compatibility, hardened container execution and
inspection, health/container-local probe, in-container runtime assertions,
loopback canonical/auth/host/origin/disabled-route/`no-store` checks, and
clean container stop/remove. Before any exposure beyond loopback, the owner
must still explicitly approve: the dedicated public hostname, TLS and proxy
configuration (Host preservation, timeouts, body limits, logging),
resource limits, restart policy, egress deny-by-default with evidence,
reviewer-token issuance/rotation, vulnerability assessment, broader
load/abuse testing, complete build-context allowlist verification, and the
§4A–§4D evidence for the exact deployment branch/commit. H8 lists the
remaining required controls; none are closed by this packaging slice beyond
the VPS checks above.

## 8. Unverified assumptions and remaining requirements

- Base image `python:3.11.14-slim-bookworm`: tag existence and linux/amd64
  availability confirmed via owner registry query from the x86_64 VPS on
  October 29, 2026; pinned to the observed index digest
  `sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d`
  (linux/amd64 manifest digest observed:
  `sha256:83f339c1be6340ae1096010fdccf6552ac932d8f410d45d206014916bdf37e48`).
  Image build (linux/amd64 `axle-h9-validation:dcc56cf`), Linux dependency
  compatibility, and container execution verified on the VPS on October 29,
  2026. Image vulnerability assessment remains pending. Registry metadata
  inspection is not an image vulnerability assessment.
- Which ignore file the platform builder honors
  (`Dockerfile.remote.dockerignore` vs root `.dockerignore`): unverified.
  Complete build-context allowlist verification remains pending: a small
  transferred context alone does not prove its exact contents.
- Corrected `requirements.remote.lock.txt` (15 pins): Mac clean install,
  `pip check` (“No broken requirements found”), exact 15-pin installed-set
  match (package-installation checks), and clean import with openai, httpx,
  PIL, and pytest absent from loaded modules (loaded-module check):
  verified on Mac (§4B). History: owner Mac clean install of the 14-pin
  candidate succeeded and `pip check` passed, selecting
  opentelemetry-api==1.45.1 transitively and revealing the missing
  explicit pin. Linux container install and Linux Python 3.11 compatibility:
  verified on the VPS on October 29, 2026 (§4C–§4D) — build-time install and
  `pip check` passed, installed runtime exactly matched all 15 pins excluding
  packaging tools, and remote import did not load openai/httpx/PIL/pytest.
- Container checks (§4C) and the network-none probe (§4D): executed on the
  x86_64 VPS on October 29, 2026 (Docker 29.8.1, Buildx v0.37.1; source
  commit `dcc56cf028548289ac367b32a4e606a1d56b47da`; image
  `axle-h9-validation:dcc56cf`): hardened network-none container ran,
  inspected running/healthy with `User=65532`, `Network=none`,
  `ReadOnly=true` and UID/GID 65532, container-local probe passed,
  in-container runtime assertions passed, loopback canonical/auth/host/origin/
  disabled-route/`no-store` checks passed, and the container stopped with
  `ExitCode=0`, was removed, leaving the exact-name listing empty. The image
  and temporary VPS source workspace remain. Docker, Podman, and Colima were
  not found on the owner Mac PATH; no Mac runtime installation was required.
- Every Coolify row in §5: unresolved; no hostname, token, TLS, proxy,
  logging, limits, restart, or egress decisions made.
- H8 remaining controls still required, including public deployment and
  external client/proxy connectivity, TLS, proxy timeouts/body limits,
  infrastructure logging review, deployment-network egress controls,
  vulnerability assessment, and broader load/abuse testing.
