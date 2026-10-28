# H8 Remote Preparation — Isolated Server-to-Server Design

Implementation is preparation only; no deployment occurred; native Muse connector is neither implemented nor approved.

Base: H1–H7 local behavior preserved. This slice adds `src/axle_hackathon/remote_app.py`, `tests/test_h8_remote.py`, and this document only. It does not change `app.py`, local demo auth, request/response contracts, economics, or model/browser behavior.

## Architecture

- Separate FastAPI entrypoint `src/axle_hackathon/remote_app.py`, isolated from the local demo app, browser interface, and model delegation harnesses.
- Reuses only `AxleEvaluationRequest`, `AxleEvaluationResponse`, and `evaluate_for_client` from `axle_api.py` (which itself uses only deterministic `economics.py` and `schemas.py`).
- No model invocation, no screenshot extraction, no booking, no storage.
- Preserves every canonical provenance field: `schema_version`, `status`, `evaluation`, `next_questions`, `source`, `confirmation_basis`, `delivery`, `model_invoked=false`, `native_connector=false`, plus full `Evaluation` fields (`synthetic`, `profile_id`, `benchmark_source`, costs, gaps, missing facts, assumptions).
- Docs, ReDoc, and OpenAPI HTTP routes are disabled (`docs_url=None`, `redoc_url=None`, `openapi_url=None`).
- All responses carry `Cache-Control: no-store` via middleware plus explicit handler headers.
- Validation and error responses are fixed and redacted: no submitted values, no authorization values, no provider bodies, no exception details. Bounded messages only (see below).
- No request-body logging. The remote module emits no logs.

## Exact configuration

Remote configuration is explicit and separate from local demo settings.

- `AXLE_API_TOKEN`: nonempty bearer token for evaluation. Surrounding whitespace is stripped; empty after stripping fails startup. Never printed or logged.
- `AXLE_API_ALLOWED_HOSTS`: comma-separated exact ASCII DNS hostnames, for example `remote-competition.test` (placeholder, not a real host). Accepted format per entry (after stripping surrounding whitespace and lowercasing): total length 1–253; dot-separated labels; each label 1–63 characters of letters/digits with interior hyphens only (`[a-z0-9]` ends, no leading/trailing hyphen). Single-label names (for example `testserver`) are accepted only when explicitly listed. Rejected: wildcards (`*`), schemes (`://`), ports (`:`), paths (`/`), query/fragment (`?`/`#`), userinfo (`@`), whitespace within names, empty labels, leading/trailing dots, malformed labels, non-ASCII, over-long labels/hosts. Matching is case-insensitive against `request.url.hostname` (port stripped) after lowercase normalization. No implicit `localhost` or `testserver` bypass; those succeed only when explicitly listed (tests list `testserver` explicitly). Never bypasses checks for local/test names.

Startup requires valid nonempty configuration. `load_remote_config()` raises `RuntimeError` on missing, empty, wildcard, or malformed host configuration; the FastAPI lifespan calls it, so startup fails. Per-request loading also validates; invalid configuration at request time returns fixed `500 {"detail":"Internal error"}` with `no-store`, never the configuration detail.

No database credentials and no model credentials are read. The remote service needs only the two variables above.

## Exact limits

All limits are enforced in code and documented here.

- Body: `MAX_BODY_BYTES = 32768` (32 KiB). Counts actual ASGI body bytes via `request.stream()`, including requests without `Content-Length`. Oversize returns fixed `413 {"detail":"Request body too large"}`. Checked before JSON parsing and schema validation, so oversize with extra fields still returns 413.
- Body deadline: `BODY_READ_TIMEOUT_SECONDS = 10.0`. Total body-read deadline enforced with `asyncio.timeout` (Python 3.11+) around the bounded read. Expiry returns fixed `408 {"detail":"Request timeout"}` with `no-store` and releases the evaluation slot. The 32 KiB actual-byte limit is retained. Proxy/server connection and header timeouts are still required in front of this app; this deadline covers only the application body read.
- Concurrency: `MAX_CONCURRENT_EVALUATIONS = 2`. Global per-process `threading.Semaphore(2)` for evaluation only. Non-blocking acquire; full returns fixed `429 {"detail":"Too many concurrent evaluations"}`.
- Rate: `RATE_LIMIT_MAX_REQUESTS = 30` per `RATE_LIMIT_WINDOW_SECONDS = 60.0`. Global per-process `collections.deque(maxlen=30)` of monotonic timestamps for evaluation only. Counts authenticated evaluation attempts that passed host, Origin, and auth checks, including invalid and oversize bodies. Full returns fixed `429 {"detail":"Rate limit exceeded"}`. Old entries beyond the window are evicted under a lock.

Scope: evaluation route only. Health checks the host allowlist but does not consume rate or concurrency quota and requires no auth.

Restart behavior: all limiter state is in-memory per process and resets on restart. No persistence.

Limitations (explicit, not claimed otherwise):

- No protection across processes or workers; N workers multiply effective capacity by N.
- No per-client fairness; one client can consume the global quota.
- No distributed denial-of-service defense.
- Memory is bounded by `maxlen=30` plus a fixed semaphore; there are no per-IP or per-token dictionaries.
- No proxy headers are read for identity; limiter identity is global, not derived from client-supplied headers.

Fixed status mapping (explicit status-to-message mapping with generic fallback):

- `401 {"detail":"Unauthorized"}` with `WWW-Authenticate: Bearer` for auth failures. `WWW-Authenticate: Bearer` is sent only for 401.
- `403 {"detail":"Forbidden"}` for host failures.
- `403 {"detail":"Origin not allowed"}` for any `Origin` header on evaluation.
- `404 {"detail":"Not Found"}` for excluded routes, `405 {"detail":"Method Not Allowed"}` for wrong methods.
- `408 {"detail":"Request timeout"}` for body-read deadline expiry.
- `413 {"detail":"Request body too large"}`, `422 {"detail":"Invalid request"}`, `429 {"detail":"Rate limit exceeded"}` or `429 {"detail":"Too many concurrent evaluations"}`, `500 {"detail":"Internal error"}` for configuration or unexpected evaluation failures.
- Unknown statuses fall back to generic `{"detail":"Error"}` (known statuses fall back to their fixed message above).

Arbitrary exception details and arbitrary exception headers are never returned; only allowlisted fixed messages are used. All success and error responses carry `Cache-Control: no-store`, including 404/405/408/500.

## Route exposure

Allowed:

- `GET /api/health` → `{"status":"ok","synthetic_only":true}` with `no-store`. Host allowlist enforced. No auth, no Origin check, no quota consumption.
- `POST /api/v1/axle/evaluate` → canonical `AxleEvaluationResponse` JSON with `no-store`. Requires host allowlist, absent `Origin`, constant-time `Bearer` comparison via `secrets.compare_digest`, rate check, concurrency slot, bounded body, strict schema validation, then deterministic evaluation.

Excluded (all `404` with `no-store`): `/docs`, `/redoc`, `/openapi.json`, `/api/v1/capabilities`, `/api/v1/freight/evaluate`, `/api/v1/agent`, `/`, `/api/v1/browser/evaluate`, `/api/v1/browser/screenshot`, and any other path. No CORS middleware is enabled. Any evaluation request containing `Origin` is denied; this initial service supports server-to-server clients only.

## HTTPS termination

The app itself serves plain HTTP via Uvicorn and terminates no TLS. When (and only when) a future deployment is approved, TLS must be terminated at the platform load balancer or reverse proxy in front of the app:

- Clients must use HTTPS to the competition hostname; the proxy must reject plain HTTP or redirect to HTTPS.
- HSTS, certificate management, and cipher policy live at the proxy, not in this codebase.
- The app must only accept connections from the proxy over a private network; direct Internet ingress to Uvicorn is out of scope.
- No TLS private keys, no certificate files, and no related secrets are stored in this repository.

No termination has been configured; no deployment occurred.

## Explicit proxy trust assumptions

- The proxy must preserve the original `Host` unchanged to the app, or the allowlist must be configured to match exactly what the app sees. The app enforces `request.url.hostname` against `AXLE_API_ALLOWED_HOSTS` with no other signal.
- The app does not read `X-Forwarded-For`, `X-Real-IP`, `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto`, or any similar proxy headers. Those headers, if present, are ignored for auth, host decisions, and limiting.
- Do not configure the proxy to override `Host` with an internal name unless that internal name is the allowlisted value; otherwise legitimate requests will fail closed with 403.
- The proxy must not strip `Authorization` or `Origin`; stripping would break auth or Origin denial semantics.
- There is no localhost or `testserver` bypass in production configuration; the allowlist must contain only the dedicated competition hostname(s).

## Separate competition service and hostname

- Remote review uses a dedicated service and hostname separate from the local demo, for example `remote-competition.test` (placeholder). No real hostname is assigned in this slice.
- Separate process, separate environment (`AXLE_API_TOKEN` / `AXLE_API_ALLOWED_HOSTS`), separate token from any local demo token. Local demo configuration does not grant remote access and remote configuration does not grant local access.
- No shared storage, no shared credentials, no shared rate state with the local app.

## Reviewer-token provisioning and revocation plan

Initial scope is a single shared reviewer token (the code supports one `AXLE_API_TOKEN` value). Per-reviewer tokens remain follow-up work.

- Generate offline with `secrets.token_urlsafe(32)` (or equivalent) on the owner machine. Never commit, never paste into chat, issues, or docs. Placeholder only in documentation.
- Store in the owner secret manager; inject as environment `AXLE_API_TOKEN` at process start. No token file in the repository.
- Provision: set the environment variable and (re)start the remote process so lifespan validates it. Verify with `GET /api/health` (host-allowed, no auth) then one `POST /api/v1/axle/evaluate` with the bearer token over HTTPS.
- Rotate: generate a new value, update the secret manager, restart the process with the new value. There is no hot reload; restart is required.
- Revoke: replace `AXLE_API_TOKEN` and restart all service instances; old tokens then return 401. Unsetting the token prevents startup. Stop the service for immediate suspension. No online revocation list.
- Compromise response: revoke as above, rotate, review proxy access logs for the exposure window (status codes and timestamps only; no bodies), and notify reviewers out of band.

No reviewer tokens have been issued; no deployment occurred.

## Safe logs

- The remote module performs no request logging and never logs bodies, headers, authorization values, tokens, hostnames from failures, submitted facts, or exception text.
- If operational logging is added later, log only bounded fixed metadata (for example route, status code, body-byte count, rate/concurrency rejections) and never values from the request or configuration.
- `Origin` values, bearer values, and oversize payload excerpts must never appear in logs. Validation failures return fixed `422` with no field details.

## No upload storage

- No file writes, no object storage, no database. Request bodies are held in memory up to 32 KiB during a single evaluation and discarded after the response.
- No screenshot bytes are accepted on this boundary (`source` is a caller assertion string, not pixel inspection). No multipart handling.
- No retention, no queue, no cache beyond the in-memory rate deque (timestamps only).

## No database or model credentials

- No database is used or configured.
- No model credentials are read and no model is invoked. Economics are deterministic via `evaluate_for_client`.
- Absence of model configuration does not affect the remote service; presence does not enable any model path.

## Rollback and stop procedure

This slice performs no deployment, so the procedure below is for a future approved deployment only.

- Stop: stop the dedicated competition service through its supervisor. Verify that all its instances are stopped and the public endpoint no longer serves application responses. A running reverse proxy may return 502/503 or a maintenance response. Leave production workloads untouched.
- Rollback: stopping the remote process is the rollback. The local demo app is a separate entrypoint and is unaffected; no shared code in `app.py` was changed.
- Verify stop: confirm no competition-service process remains running, health no longer returns the application success response, and evaluation is unavailable. A proxy error response is compatible with a stopped backend.
- Credentials after stop: rotate the reviewer token if the stop was due to suspected exposure; otherwise retain the secret-manager value for the next approved start.

## Remaining controls required before deployment

The following are required before any exposure beyond loopback, and are explicitly not done in this slice:

- A dedicated minimal runtime image and lockfile for the remote service. Current package dependencies are not claimed to be minimal. A dedicated minimal runtime image/lock and verified egress restrictions remain follow-up work.
- Verified egress restrictions (deny-by-default outbound, allow only required update endpoints if any) with evidence.
- Distributed rate limiting and abuse defense if more than one worker or host is used; the current limiter is per-process only.
- Web application firewall, TLS/HSTS verification, and proxy Host-preservation verification.
- Centralized audit logging (status-only, no bodies) with retention and alerting.
- Per-reviewer tokens or short-lived credentials if shared-token risk is unacceptable.
- Load and soak testing of the exact limits (32 KiB, 10 s body deadline, 2 concurrent, 30/min) plus proxy/server connection and header timeouts (still required; the app deadline covers only the body read).
- Security review of the proxy configuration, secret handling, and incident runbook.
- Owner authorization for the concrete deployment, dedicated hostname and reviewer access remains required. Startup Track eligibility and reuse of existing VPS hosting are resolved owner-supplied clarifications.

Implementation is preparation only; no deployment occurred; native Muse connector is neither implemented nor approved.


Operational logging caveat: the module emits no logs, but the ASGI server, framework and proxy may log access information or unhandled exception tracebacks. Redacted HTTP responses do not establish safe infrastructure logs. Verify logging configuration before deployment.
