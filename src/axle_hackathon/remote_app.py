"""Isolated server-to-server evaluation boundary. Preparation only; no deployment.

Exposes only GET /api/health and POST /api/v1/axle/evaluate. Docs disabled.

Configuration (explicit, separate from local demo settings):
  AXLE_API_TOKEN: nonempty bearer token for evaluation requests.
  AXLE_API_ALLOWED_HOSTS: comma-separated exact ASCII DNS hostnames.
    Each name: total 1-253 chars, dot-separated labels of 1-63 letters/
    digits with interior hyphens only, lowercased. Single-label names
    (for example testserver) accepted only when explicitly listed.
    Rejects wildcards, schemes, ports, paths, userinfo, whitespace,
    empty labels, leading/trailing dots, malformed labels. Never
    bypasses checks for local/test names.
Both are required at startup. Invalid configuration fails startup.

Exact limits:
  MAX_BODY_BYTES = 32768 (32 KiB). Counts actual ASGI body bytes via
    request.stream(), including requests without Content-Length. 413 when over.
  BODY_READ_TIMEOUT_SECONDS = 10.0. Total body-read deadline via
    asyncio.timeout (Python 3.11+). Fixed 408 JSON on expiry; the
    evaluation slot is released. Proxy/server connection and header
    timeouts are still required in front of this app.
  MAX_CONCURRENT_EVALUATIONS = 2. Global per-process semaphore for
    evaluation only. Non-blocking acquire; 429 when full.
  RATE_LIMIT_MAX_REQUESTS = 30 per RATE_LIMIT_WINDOW_SECONDS = 60.0.
    Global per-process deque with maxlen=30 for evaluation only.
    Counts authenticated evaluation attempts that passed host/origin/auth
    checks, including invalid and oversized bodies. 429 when full.

Errors: fixed status-to-message mapping with generic fallback. Arbitrary
  exception details and headers are never returned. WWW-Authenticate:
  Bearer is sent only for 401. Cache-Control: no-store on success and
  error responses, including 404/405/500.

Scope: evaluation route only; health checks host allowlist but does not
  consume rate or concurrency quota. No per-client tables; memory is bounded
  by maxlen and a fixed semaphore. No proxy headers are read; limiter
  identity is global, not derived from client-supplied headers.

Restart behavior: all limiter state is in-memory per process and resets on
  restart. No persistence.

Limitations: no protection across processes or workers; N workers multiply
  effective capacity by N. No per-client fairness; one client can consume the
  global quota. No distributed denial-of-service defense.
"""

import asyncio
import collections
import json
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from .axle_api import AxleEvaluationRequest, AxleEvaluationResponse, evaluate_for_client

MAX_BODY_BYTES = 32 * 1024
BODY_READ_TIMEOUT_SECONDS = 10.0
MAX_CONCURRENT_EVALUATIONS = 2
RATE_LIMIT_MAX_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60.0

_TOKEN_ENV = "AXLE_API_TOKEN"
_HOSTS_ENV = "AXLE_API_ALLOWED_HOSTS"

_HOST_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")

_REQUEST_TIMES: collections.deque[float] = collections.deque(maxlen=RATE_LIMIT_MAX_REQUESTS)
_RATE_LOCK = threading.Lock()
_EVAL_SLOTS = threading.Semaphore(MAX_CONCURRENT_EVALUATIONS)
_clock = time.monotonic


def _is_valid_hostname(host: str) -> bool:
    if not host or len(host) > 253:
        return False
    try:
        host.encode("ascii")
    except (UnicodeError, ValueError):
        return False
    if any(ch.isspace() for ch in host):
        return False
    if host.startswith(".") or host.endswith("."):
        return False
    if any(token in host for token in ("://", "/", ":", "@", "?", "#", "*")):
        return False
    for label in host.split("."):
        if not label or len(label) > 63:
            return False
        if _HOST_LABEL_RE.fullmatch(label) is None:
            return False
    return True


def load_remote_config() -> tuple[str, frozenset[str]]:
    token = os.environ.get(_TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError("Remote token is not configured")
    raw_hosts = os.environ.get(_HOSTS_ENV, "")
    if not raw_hosts.strip():
        raise RuntimeError("Remote allowed hosts are not configured")
    normalized: list[str] = []
    for entry in raw_hosts.split(","):
        stripped = entry.strip()
        if not stripped:
            raise RuntimeError("Remote allowed hosts are not configured")
        lowered = stripped.lower()
        if "*" in lowered:
            raise RuntimeError("Wildcard hosts are not allowed")
        if not _is_valid_hostname(lowered):
            raise RuntimeError("Invalid allowed host")
        normalized.append(lowered)
    return token, frozenset(normalized)


def _body_timeout():
    return asyncio.timeout(BODY_READ_TIMEOUT_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_remote_config()
    yield
    return


app = FastAPI(
    title="Axle Remote Evaluation",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def _no_store(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def _request_validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request"},
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(ValidationError)
async def _pydantic_validation_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request"},
        headers={"Cache-Control": "no-store"},
    )


_FIXED_DETAIL_ALLOWLIST: dict[int, frozenset[str]] = {
    401: frozenset({"Unauthorized"}),
    403: frozenset({"Forbidden", "Origin not allowed"}),
    404: frozenset({"Not Found"}),
    405: frozenset({"Method Not Allowed"}),
    408: frozenset({"Request timeout"}),
    413: frozenset({"Request body too large"}),
    422: frozenset({"Invalid request"}),
    429: frozenset({"Rate limit exceeded", "Too many concurrent evaluations"}),
    500: frozenset({"Internal error"}),
}

_FALLBACK_DETAIL: dict[int, str] = {
    400: "Invalid request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request timeout",
    413: "Request body too large",
    422: "Invalid request",
    429: "Too many requests",
    500: "Internal error",
}

_GENERIC_FALLBACK = "Error"


@app.exception_handler(HTTPException)
async def _http_handler(request: Request, exc: HTTPException):
    allowed = _FIXED_DETAIL_ALLOWLIST.get(exc.status_code)
    if allowed is not None and isinstance(exc.detail, str) and exc.detail in allowed:
        detail = exc.detail
    else:
        detail = _FALLBACK_DETAIL.get(exc.status_code, _GENERIC_FALLBACK)
    headers: dict[str, str] = {"Cache-Control": "no-store"}
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=headers)


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal error"},
        headers={"Cache-Control": "no-store"},
    )


def _check_host(request: Request, allowed: frozenset[str]) -> None:
    hostname = (request.url.hostname or "").lower()
    if hostname not in allowed:
        raise HTTPException(403, "Forbidden")


def _check_origin_absent(request: Request) -> None:
    if "origin" in request.headers:
        raise HTTPException(403, "Origin not allowed")


def _check_auth(request: Request, token: str) -> None:
    auth = request.headers.get("authorization", "")
    expected = "Bearer " + token
    try:
        valid = secrets.compare_digest(auth.encode("utf-8"), expected.encode("utf-8"))
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})


def _check_rate() -> None:
    now = _clock()
    with _RATE_LOCK:
        while _REQUEST_TIMES and now - _REQUEST_TIMES[0] > RATE_LIMIT_WINDOW_SECONDS:
            _REQUEST_TIMES.popleft()
        if len(_REQUEST_TIMES) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(429, "Rate limit exceeded")
        _REQUEST_TIMES.append(now)


@contextmanager
def _eval_slot():
    if not _EVAL_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Too many concurrent evaluations")
    try:
        yield
    finally:
        _EVAL_SLOTS.release()


async def _read_bounded(request: Request) -> bytes:
    parts: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(413, "Request body too large")
        if chunk:
            parts.append(chunk)
    return b"".join(parts)


def _load_or_500() -> tuple[str, frozenset[str]]:
    try:
        return load_remote_config()
    except RuntimeError:
        raise HTTPException(500, "Internal error") from None


@app.get("/api/health")
async def health(request: Request):
    _, allowed = _load_or_500()
    _check_host(request, allowed)
    return JSONResponse(
        {"status": "ok", "synthetic_only": True},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/v1/axle/evaluate")
async def remote_evaluate(request: Request):
    token, allowed = _load_or_500()
    _check_host(request, allowed)
    _check_origin_absent(request)
    _check_auth(request, token)
    _check_rate()
    with _eval_slot():
        try:
            async with _body_timeout():
                raw = await _read_bounded(request)
        except TimeoutError:
            raise HTTPException(408, "Request timeout") from None
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, "Invalid request") from None
        try:
            body = AxleEvaluationRequest.model_validate(data)
        except (ValidationError, ValueError):
            raise HTTPException(422, "Invalid request") from None
        except Exception:
            raise HTTPException(422, "Invalid request") from None
        try:
            result: AxleEvaluationResponse = evaluate_for_client(body)
        except Exception:
            raise HTTPException(500, "Internal error") from None
        return JSONResponse(
            result.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
