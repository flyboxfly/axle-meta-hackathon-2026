"""H8 isolated remote boundary tests. No deployment, no model calls."""
import asyncio
import ast
import collections
import json
import pathlib
import threading
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from axle_hackathon import remote_app
from test_h1 import BASE, COMPLETE


TOKEN = "test-remote-token"
ALLOW = "testserver,allowed.test"


def payload(target="2.00", opportunity=None):
    return {
        "opportunity": COMPLETE if opportunity is None else opportunity,
        "benchmark": {"target_all_mile_rpm": target, "confirmed": True},
        "facts_confirmed": True,
        "source": "screenshot",
    }


@pytest.fixture
def remote_env(monkeypatch):
    monkeypatch.setenv("AXLE_API_TOKEN", TOKEN)
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", ALLOW)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("AXLE_DEMO_TOKEN", "local-only-token")
    remote_app._REQUEST_TIMES.clear()
    remote_app._EVAL_SLOTS = threading.Semaphore(remote_app.MAX_CONCURRENT_EVALUATIONS)
    yield
    remote_app._REQUEST_TIMES.clear()
    remote_app._EVAL_SLOTS = threading.Semaphore(remote_app.MAX_CONCURRENT_EVALUATIONS)


@pytest.fixture
def client(remote_env):
    return TestClient(remote_app.app, headers={"Authorization": "Bearer " + TOKEN})


def asgi_call(method, path, body: bytes, headers: dict[str, str]):
    raw = [(k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in headers.items()]
    assert all(k != b"content-length" for k, _ in raw)
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": raw,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    chunks = [body[i : i + 8192] for i in range(0, len(body), 8192)] or [b""]
    queue = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]

    async def receive():
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    messages: list[dict] = []

    async def send(message):
        messages.append(message)

    async def run():
        await remote_app.app(scope, receive, send)

    asyncio.run(run())
    status = None
    resp_headers: dict[str, str] = {}
    resp_body = b""
    for message in messages:
        if message["type"] == "http.response.start":
            status = message["status"]
            for k, v in message.get("headers", []):
                resp_headers[k.decode("utf-8").lower()] = v.decode("utf-8")
        elif message["type"] == "http.response.body":
            resp_body += message.get("body", b"")
    assert status is not None
    return status, resp_headers, resp_body


def _slots_free() -> bool:
    acquired = 0
    try:
        for _ in range(remote_app.MAX_CONCURRENT_EVALUATIONS):
            if remote_app._EVAL_SLOTS.acquire(blocking=False):
                acquired += 1
            else:
                return False
        return True
    finally:
        for _ in range(acquired):
            remote_app._EVAL_SLOTS.release()


@asynccontextmanager
async def _noop_body_timeout():
    yield


@asynccontextmanager
async def _expired_body_timeout():
    raise TimeoutError("injected deadline")
    yield  # pragma: no cover


def _auth_headers() -> dict[str, str]:
    return {"host": "testserver", "authorization": "Bearer " + TOKEN, "content-type": "application/json"}


async def _asgi_request_async(method, path, body: bytes, headers: dict[str, str], receive_hook=None):
    raw = [(k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in headers.items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": raw,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    chunks = [body[i : i + 8192] for i in range(0, len(body), 8192)] or [b""]
    queue = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]

    async def receive():
        if receive_hook is not None:
            hooked = await receive_hook()
            if hooked is not None:
                return hooked
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    messages: list[dict] = []

    async def send(message):
        messages.append(message)

    await remote_app.app(scope, receive, send)
    status = None
    resp_headers: dict[str, str] = {}
    resp_body = b""
    for message in messages:
        if message["type"] == "http.response.start":
            status = message["status"]
            for k, v in message.get("headers", []):
                resp_headers[k.decode("utf-8").lower()] = v.decode("utf-8")
        elif message["type"] == "http.response.body":
            resp_body += message.get("body", b"")
    assert status is not None
    return status, resp_headers, resp_body


def test_startup_config_validation(monkeypatch):
    monkeypatch.setenv("AXLE_API_TOKEN", TOKEN)
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "allowed.test")
    token, allowed = remote_app.load_remote_config()
    assert token == TOKEN and allowed == frozenset({"allowed.test"})
    for bad_token in ["", "   "]:
        monkeypatch.setenv("AXLE_API_TOKEN", bad_token)
        with pytest.raises(RuntimeError):
            remote_app.load_remote_config()
    monkeypatch.setenv("AXLE_API_TOKEN", TOKEN)
    monkeypatch.delenv("AXLE_API_TOKEN")
    with pytest.raises(RuntimeError):
        remote_app.load_remote_config()
    monkeypatch.setenv("AXLE_API_TOKEN", TOKEN)
    for bad_hosts in ["", "   ", "allowed.test,,other.test", " , "]:
        monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", bad_hosts)
        with pytest.raises(RuntimeError):
            remote_app.load_remote_config()
    for wild in ["*", "allowed.test,*", "*,allowed.test", "**.test"]:
        monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", wild)
        with pytest.raises(RuntimeError):
            remote_app.load_remote_config()
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "ALLOWED.TEST")
    _, allowed = remote_app.load_remote_config()
    assert allowed == frozenset({"allowed.test"})
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "testserver")
    _, allowed = remote_app.load_remote_config()
    assert allowed == frozenset({"testserver"})
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "  allowed.test , Other.Test  ")
    _, allowed = remote_app.load_remote_config()
    assert allowed == frozenset({"allowed.test", "other.test"})
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "a-b.test,1abc.test,x1.test")
    _, allowed = remote_app.load_remote_config()
    assert allowed == frozenset({"a-b.test", "1abc.test", "x1.test"})
    long_label = "a" * 64
    long_host = ".".join(["a" * 63] * 4) + ".test"
    assert len(long_host) > 253
    exact_253 = "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 61
    assert len(exact_253) == 253
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", exact_253)
    _, allowed = remote_app.load_remote_config()
    assert allowed == frozenset({exact_253})
    exact_63_label = "a" * 63 + ".test"
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", exact_63_label)
    _, allowed = remote_app.load_remote_config()
    assert allowed == frozenset({exact_63_label})
    malformed = [
        "https://allowed.test",
        "http://allowed.test",
        "allowed.test:443",
        "allowed.test/path",
        "allowed.test?x=1",
        "allowed.test#frag",
        "user@allowed.test",
        "user:pass@allowed.test",
        "allow ed.test",
        "allowed\t.test",
        ".allowed.test",
        "allowed.test.",
        "allowed..test",
        "-allowed.test",
        "allowed-.test",
        "allow_ed.test",
        "allowed.test-",
        "a--.test",
        long_label + ".test",
        long_host,
        "exämple.test",
        "allowed.test,",
        ",allowed.test",
        "allowed.test, ",
    ]
    for bad in malformed:
        monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", bad)
        with pytest.raises(RuntimeError):
            remote_app.load_remote_config()
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "allowed.test,bad..test")
    with pytest.raises(RuntimeError):
        remote_app.load_remote_config()
    monkeypatch.delenv("AXLE_API_ALLOWED_HOSTS")
    with pytest.raises(RuntimeError):
        remote_app.load_remote_config()


def test_startup_lifespan_rejects_bad_config(monkeypatch):
    monkeypatch.setenv("AXLE_API_TOKEN", TOKEN)
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "allowed.test")
    with TestClient(remote_app.app) as ok:
        assert ok.get("/api/health", headers={"Host": "allowed.test"}).status_code == 200
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "*")
    with pytest.raises(RuntimeError):
        with TestClient(remote_app.app):
            pass
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "allowed.test")
    monkeypatch.delenv("AXLE_API_TOKEN")
    with pytest.raises(RuntimeError):
        with TestClient(remote_app.app):
            pass


def test_bad_config_request_returns_500_fixed(client, monkeypatch):
    monkeypatch.delenv("AXLE_API_TOKEN")
    r = client.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error"}
    assert r.headers["cache-control"] == "no-store"


def test_host_allowlist(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"Host": "allowed.test"}).status_code == 200
    assert client.get("/api/health", headers={"Host": "ALLOWED.TEST"}).status_code == 200
    for bad in ["other.test", "localhost", "127.0.0.1"]:
        r = client.get("/api/health", headers={"Host": bad})
        assert r.status_code == 403
        assert r.json() == {"detail": "Forbidden"}
        assert r.headers["cache-control"] == "no-store"
    r = client.post("/api/v1/axle/evaluate", json=payload(), headers={"Host": "other.test"})
    assert r.status_code == 403
    assert r.json() == {"detail": "Forbidden"}
    assert r.headers["cache-control"] == "no-store"
    assert "access-control-allow-origin" not in r.headers


def test_no_implicit_localhost_bypass(remote_env, monkeypatch):
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "allowed.test")
    c = TestClient(remote_app.app, headers={"Authorization": "Bearer " + TOKEN})
    assert c.get("/api/health", headers={"Host": "allowed.test"}).status_code == 200
    assert c.get("/api/health").status_code == 403
    assert c.get("/api/health", headers={"Host": "localhost"}).status_code == 403
    assert c.post("/api/v1/axle/evaluate", json=payload()).status_code == 403


def test_origin_denied_on_evaluation_only(client):
    for origin in ["https://allowed.test", "https://other.test", "null"]:
        r = client.post("/api/v1/axle/evaluate", json=payload(), headers={"Origin": origin})
        assert r.status_code == 403
        assert r.json() == {"detail": "Origin not allowed"}
        assert r.headers["cache-control"] == "no-store"
        assert origin not in r.text
    assert client.get("/api/health", headers={"Origin": "https://allowed.test"}).status_code == 200


def test_auth_bearer_required(client):
    c = TestClient(remote_app.app)
    r = c.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 401
    assert r.json() == {"detail": "Unauthorized"}
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.headers["cache-control"] == "no-store"
    for bad in ["Bearer wrong-token", "Basic dGVzdA==", "Bearer local-only-token", "Bearer "]:
        r = c.post("/api/v1/axle/evaluate", json=payload(), headers={"Authorization": bad})
        assert r.status_code == 401
        assert bad not in r.text or "Bearer" in bad
        assert TOKEN not in r.text
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200
    assert client.get("/api/health").status_code == 200


def test_body_size_with_content_length(client):
    base = json.dumps(payload()).encode("utf-8")
    assert len(base) < remote_app.MAX_BODY_BYTES
    pad = remote_app.MAX_BODY_BYTES - len(base)
    exact = base + b" " * pad
    assert len(exact) == remote_app.MAX_BODY_BYTES
    r = client.post(
        "/api/v1/axle/evaluate",
        content=exact,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    over = base + b" " * (pad + 1)
    r = client.post(
        "/api/v1/axle/evaluate",
        content=over,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json() == {"detail": "Request body too large"}
    assert r.headers["cache-control"] == "no-store"
    big = payload()
    big["padding"] = "x" * 40000
    r = client.post("/api/v1/axle/evaluate", json=big)
    assert r.status_code == 413
    assert "xxxx" not in r.text


def test_body_size_without_content_length(remote_env):
    small = json.dumps(payload()).encode("utf-8")
    headers = {"host": "testserver", "authorization": "Bearer " + TOKEN, "content-type": "application/json"}
    status, resp_headers, body = asgi_call("POST", "/api/v1/axle/evaluate", small, headers)
    assert status == 200
    assert resp_headers.get("cache-control") == "no-store"
    large = small + b" " * (remote_app.MAX_BODY_BYTES - len(small) + 1)
    assert len(large) > remote_app.MAX_BODY_BYTES
    status, resp_headers, body = asgi_call("POST", "/api/v1/axle/evaluate", large, headers)
    assert status == 413
    assert resp_headers.get("cache-control") == "no-store"
    assert json.loads(body) == {"detail": "Request body too large"}
    assert b"420" not in body


def test_sanitized_validation_errors(client):
    cases = [
        {"benchmark": None},
        {"benchmark": {"confirmed": True}},
        {"benchmark": {"target_all_mile_rpm": "2", "confirmed": False}},
        {"benchmark": {"target_all_mile_rpm": "2", "confirmed": "true"}},
        {"facts_confirmed": False},
        {"facts_confirmed": 1},
        {"carrier_id": "other"},
        {"source": "model_verified"},
        {"benchmark": {"target_all_mile_rpm": "2.001", "confirmed": True}},
    ]
    for change in cases:
        body = payload() | change
        r = client.post("/api/v1/axle/evaluate", json=body)
        assert r.status_code == 422
        assert r.json() == {"detail": "Invalid request"}
        assert r.headers["cache-control"] == "no-store"
        assert len(r.content) < 1024
        for secret in ["other", "2.001", "model_verified", "carrier_id"]:
            assert secret not in r.text
    for raw in [b"{invalid", b"", b"null", b"[]"]:
        r = client.post("/api/v1/axle/evaluate", content=raw, headers={"Content-Type": "application/json"})
        assert r.status_code == 422
        assert r.json() == {"detail": "Invalid request"}


def test_no_store_everywhere(client, monkeypatch):
    assert client.get("/api/health").headers["cache-control"] == "no-store"
    assert client.post("/api/v1/axle/evaluate", json=payload()).headers["cache-control"] == "no-store"
    c = TestClient(remote_app.app)
    assert c.post("/api/v1/axle/evaluate", json=payload()).headers["cache-control"] == "no-store"
    assert client.get("/api/health", headers={"Host": "other.test"}).headers["cache-control"] == "no-store"
    assert client.post("/api/v1/axle/evaluate", json=payload(), headers={"Origin": "https://allowed.test"}).headers[
        "cache-control"
    ] == "no-store"
    assert client.post("/api/v1/axle/evaluate", json={"bad": 1}).headers["cache-control"] == "no-store"
    assert client.get("/openapi.json").headers["cache-control"] == "no-store"
    now = [2000.0]
    monkeypatch.setattr(remote_app, "_clock", lambda: now[0])
    remote_app._REQUEST_TIMES.extend([now[0]] * remote_app.RATE_LIMIT_MAX_REQUESTS)
    assert client.post("/api/v1/axle/evaluate", json=payload()).headers["cache-control"] == "no-store"


def test_bounded_rate_limiter(client, monkeypatch):
    now = [3000.0]
    monkeypatch.setattr(remote_app, "_clock", lambda: now[0])
    assert remote_app._REQUEST_TIMES.maxlen == remote_app.RATE_LIMIT_MAX_REQUESTS
    remote_app._REQUEST_TIMES.extend([now[0]] * remote_app.RATE_LIMIT_MAX_REQUESTS)
    assert len(remote_app._REQUEST_TIMES) <= remote_app.RATE_LIMIT_MAX_REQUESTS
    r = client.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 429
    assert r.json() == {"detail": "Rate limit exceeded"}
    assert r.headers["cache-control"] == "no-store"
    assert len(remote_app._REQUEST_TIMES) <= remote_app.RATE_LIMIT_MAX_REQUESTS
    assert client.get("/api/health").status_code == 200
    now[0] += remote_app.RATE_LIMIT_WINDOW_SECONDS + 1
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200
    remote_app._REQUEST_TIMES.extend([now[0]] * remote_app.RATE_LIMIT_MAX_REQUESTS)
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 429
    remote_app._REQUEST_TIMES.clear()
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200


def test_bounded_concurrency(client):
    held = []
    for _ in range(remote_app.MAX_CONCURRENT_EVALUATIONS):
        assert remote_app._EVAL_SLOTS.acquire(blocking=False)
        held.append(True)
    try:
        assert not remote_app._EVAL_SLOTS.acquire(blocking=False)
        r = client.post("/api/v1/axle/evaluate", json=payload())
        assert r.status_code == 429
        assert r.json() == {"detail": "Too many concurrent evaluations"}
        assert r.headers["cache-control"] == "no-store"
        assert client.get("/api/health").status_code == 200
    finally:
        for _ in held:
            remote_app._EVAL_SLOTS.release()
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200


def test_excluded_routes(client):
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/api/v1/capabilities").status_code == 404
    assert client.post("/api/v1/freight/evaluate", json=BASE).status_code == 404
    assert client.post("/api/v1/agent", json={"message": "hi"}).status_code == 404
    assert client.get("/").status_code == 404
    assert client.post("/api/v1/browser/evaluate", json={}).status_code == 404
    assert remote_app.app.docs_url is None
    assert remote_app.app.redoc_url is None
    assert remote_app.app.openapi_url is None
    routes = sorted(
        (r.path, tuple(sorted(r.methods)))
        for r in remote_app.app.routes
        if hasattr(r, "path")
    )
    assert routes == [("/api/health", ("GET",)), ("/api/v1/axle/evaluate", ("POST",))]


def test_canonical_economics_sequence(client):
    results = [client.post("/api/v1/axle/evaluate", json=payload(t)) for t in ["2.00", "1.75", None]]
    assert all(r.status_code == 200 and r.headers["cache-control"] == "no-store" for r in results)
    bodies = [r.json() for r in results]
    values = [b["evaluation"] for b in bodies]
    assert [v["decision"] for v in values] == ["NEGOTIATE", "ACCEPT", "NEED_MORE_INFORMATION"]
    assert [v["revenue_gap_to_target"] for v in values] == ["60.00", "0.00", None]
    assert all(
        v["estimated_operating_cost"] == "290.00"
        and v["estimated_operating_surplus_after_allocated_costs"] == "130.00"
        for v in values
    )
    assert all(v["synthetic"] is True and v["profile_id"] == "synthetic-box-001" for v in values)
    assert [v["benchmark_source"] for v in values] == ["carrier_confirmed", "carrier_confirmed", "carrier_unknown"]
    assert all(
        b["schema_version"] == "1.0"
        and b["status"] == "evaluated"
        and b["confirmation_basis"] == "caller_assertion"
        and b["delivery"] == "canonical_api"
        and b["model_invoked"] is False
        and b["native_connector"] is False
        and b["source"] == "screenshot"
        for b in bodies
    )
    assert bodies[0]["next_questions"] == []
    assert bodies[-1]["next_questions"][0]["field"] == "carrier_revenue_target"


def test_strict_unknown_and_extra(client):
    for key in ["benchmark", "facts_confirmed", "source"]:
        body = payload()
        del body[key]
        assert client.post("/api/v1/axle/evaluate", json=body).status_code == 422
    r = client.post("/api/v1/axle/evaluate", json=payload(opportunity=BASE)).json()
    assert r["evaluation"]["estimated_operating_cost"] is None
    assert r["next_questions"][0]["field"] == "diesel_per_gallon"
    op = COMPLETE | {"equipment": "power_only_amazon_provided_trailer"}
    r = client.post("/api/v1/axle/evaluate", json=payload(opportunity=op)).json()
    assert r["evaluation"]["decision"] == "NEED_MORE_INFORMATION"
    assert r["next_questions"][0]["field"] == "matching_equipment_carrier_profile"
    for extra in [{"bid": 100}, {"carrier_id": "x"}, {"benchmark": {"target_all_mile_rpm": "2.00", "confirmed": True, "x": 1}}]:
        body = payload()
        if "benchmark" in extra and isinstance(extra["benchmark"], dict):
            body["benchmark"] = extra["benchmark"]
        else:
            body["opportunity"] = dict(COMPLETE, **extra)
        assert client.post("/api/v1/axle/evaluate", json=body).status_code == 422


def test_rate_quota_actual_requests_window_expiry(client, monkeypatch):
    now = [4000.0]
    monkeypatch.setattr(remote_app, "_clock", lambda: now[0])
    for i in range(remote_app.RATE_LIMIT_MAX_REQUESTS):
        r = client.post("/api/v1/axle/evaluate", json=payload())
        assert r.status_code == 200, i
    assert len(remote_app._REQUEST_TIMES) == remote_app.RATE_LIMIT_MAX_REQUESTS
    r = client.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 429
    assert r.json() == {"detail": "Rate limit exceeded"}
    assert r.headers["cache-control"] == "no-store"
    now[0] += remote_app.RATE_LIMIT_WINDOW_SECONDS
    r = client.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 429
    assert r.json() == {"detail": "Rate limit exceeded"}
    now[0] += 0.001
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200
    for _ in range(remote_app.RATE_LIMIT_MAX_REQUESTS - 1):
        assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 429
    assert client.get("/api/health").status_code == 200
    now[0] += remote_app.RATE_LIMIT_WINDOW_SECONDS + 1
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200


def test_fixed_error_redaction(client, monkeypatch):
    async def _run_handler(status, detail, headers):
        exc = HTTPException(status_code=status, detail=detail, headers=headers)
        resp = await asyncio.wait_for(remote_app._http_handler(None, exc), timeout=5)  # type: ignore[arg-type]
        body = resp.body.decode("utf-8")
        lowered = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status_code, body, lowered

    async def _cases():
        cases = [
            (403, "super-secret-detail-abc123", {"X-Secret": "top-secret-value", "X-Custom": "leak"}),
            (500, "traceback TOKEN=secret-xyz", {"X-Internal": "secret-xyz"}),
            (429, "sensitive-quota-detail", {"Retry-After": "1", "X-Leak": "secret"}),
            (404, "sensitive-missing-detail", {"X-Data": "secret"}),
            (405, "sensitive-method-detail", {"Allow": "GET", "X-Data": "secret"}),
            (418, "teapot-secret-detail", {"X-Teapot": "secret"}),
        ]
        results = []
        for status, detail, headers in cases:
            results.append(await _run_handler(status, detail, headers))
        return results

    results = asyncio.run(asyncio.wait_for(_cases(), timeout=10))
    expected = {
        403: "Forbidden",
        500: "Internal error",
        429: "Too many requests",
        404: "Not Found",
        405: "Method Not Allowed",
        418: "Error",
    }
    statuses = [403, 500, 429, 404, 405, 418]
    for (status_code, body, lowered), status in zip(results, statuses):
        assert status_code == status
        assert json.loads(body) == {"detail": expected[status]}
        assert "secret" not in body.lower()
        assert "traceback" not in body.lower()
        assert "teapot-secret" not in body
        assert lowered.get("cache-control") == "no-store"
        assert "x-secret" not in lowered
        assert "x-custom" not in lowered
        assert "x-internal" not in lowered
        assert "x-leak" not in lowered
        assert "x-data" not in lowered
        assert "x-teapot" not in lowered
        assert "www-authenticate" not in lowered
    code, body, lowered = asyncio.run(_run_handler(401, "evil-detail-secret", {"WWW-Authenticate": "Basic evil", "X-Evil": "secret"}))
    assert code == 401
    assert json.loads(body) == {"detail": "Unauthorized"}
    assert "secret" not in body.lower()
    assert "evil" not in body.lower()
    assert lowered.get("www-authenticate") == "Bearer"
    assert lowered.get("cache-control") == "no-store"
    assert "x-evil" not in lowered

    def _sensitive_rate():
        raise HTTPException(429, "sensitive-end-to-end-secret", headers={"X-Leak": "end-to-end-secret"})

    monkeypatch.setattr(remote_app, "_check_rate", _sensitive_rate)
    r = client.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 429
    assert r.json() == {"detail": "Too many requests"}
    assert "secret" not in r.text.lower()
    assert "x-leak" not in {k.lower() for k in r.headers}
    assert r.headers["cache-control"] == "no-store"


def test_no_store_error_statuses(client, monkeypatch):
    r = client.get("/openapi.json")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    assert r.headers["cache-control"] == "no-store"
    assert "www-authenticate" not in {k.lower() for k in r.headers}
    r = client.get("/api/v1/axle/evaluate")
    assert r.status_code == 405
    assert r.json() == {"detail": "Method Not Allowed"}
    assert r.headers["cache-control"] == "no-store"
    assert "www-authenticate" not in {k.lower() for k in r.headers}
    monkeypatch.delenv("AXLE_API_TOKEN")
    r = client.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error"}
    assert r.headers["cache-control"] == "no-store"
    assert "www-authenticate" not in {k.lower() for k in r.headers}
    monkeypatch.setenv("AXLE_API_TOKEN", TOKEN)
    original_timeout = remote_app._body_timeout
    monkeypatch.setattr(remote_app, "_body_timeout", _expired_body_timeout)
    try:
        r = client.post("/api/v1/axle/evaluate", json=payload())
    finally:
        monkeypatch.setattr(remote_app, "_body_timeout", original_timeout)
    assert r.status_code == 408
    assert r.json() == {"detail": "Request timeout"}
    assert r.headers["cache-control"] == "no-store"
    assert "www-authenticate" not in {k.lower() for k in r.headers}


def test_body_timeout_fixed_408_retains_byte_limit(client, monkeypatch):
    assert remote_app.BODY_READ_TIMEOUT_SECONDS == 10.0
    original_timeout = remote_app._body_timeout
    monkeypatch.setattr(remote_app, "_body_timeout", _expired_body_timeout)
    try:
        r = client.post("/api/v1/axle/evaluate", json=payload())
        assert r.status_code == 408
        assert r.json() == {"detail": "Request timeout"}
        assert r.headers["cache-control"] == "no-store"
        assert _slots_free()
    finally:
        monkeypatch.setattr(remote_app, "_body_timeout", original_timeout)
    base = json.dumps(payload()).encode("utf-8")
    pad = remote_app.MAX_BODY_BYTES - len(base)
    exact = base + b" " * pad
    r = client.post("/api/v1/axle/evaluate", content=exact, headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    over = base + b" " * (pad + 1)
    r = client.post("/api/v1/axle/evaluate", content=over, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json() == {"detail": "Request body too large"}


def test_slots_released_after_failures(client, monkeypatch):
    assert _slots_free()
    base = json.dumps(payload()).encode("utf-8")
    over = base + b" " * (remote_app.MAX_BODY_BYTES - len(base) + 1)
    r = client.post("/api/v1/axle/evaluate", content=over, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert _slots_free()
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200
    r = client.post("/api/v1/axle/evaluate", content=b"{invalid", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert _slots_free()
    original_evaluate = remote_app.evaluate_for_client

    def _boom(body):
        raise RuntimeError("simulated evaluator failure")

    monkeypatch.setattr(remote_app, "evaluate_for_client", _boom)
    r = client.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error"}
    assert _slots_free()
    monkeypatch.setattr(remote_app, "evaluate_for_client", original_evaluate)
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200
    original_timeout = remote_app._body_timeout
    monkeypatch.setattr(remote_app, "_body_timeout", _expired_body_timeout)
    r = client.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 408
    assert _slots_free()
    monkeypatch.setattr(remote_app, "_body_timeout", original_timeout)
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200
    original_read = remote_app._read_bounded
    sentinel = "sentinel-unexpected-read-failure-9f8e7d6c"

    async def _boom_read(request):
        raise RuntimeError(sentinel)

    # Unexpected RuntimeError is not a client disconnect. With the default
    # TestClient behavior (raise_server_exceptions=True) it propagates to
    # the caller; slots must still be released.
    monkeypatch.setattr(remote_app, "_read_bounded", _boom_read)
    with pytest.raises(RuntimeError, match="sentinel-unexpected-read-failure"):
        client.post("/api/v1/axle/evaluate", json=payload())
    assert _slots_free()

    # Narrowly scoped client surfacing the app's fixed 500 mapping.
    quiet = TestClient(
        remote_app.app,
        headers={"Authorization": "Bearer " + TOKEN},
        raise_server_exceptions=False,
    )
    r = quiet.post("/api/v1/axle/evaluate", json=payload())
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error"}
    assert r.headers["cache-control"] == "no-store"
    assert sentinel not in r.text
    assert "traceback" not in r.text.lower()
    assert _slots_free()

    monkeypatch.setattr(remote_app, "_read_bounded", original_read)
    assert client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200
    assert _slots_free()


def test_disconnect_during_incomplete_body_releases_slot(remote_env):
    """Real ASGI http.disconnect during an incomplete body releases the slot."""
    assert _slots_free()
    full = json.dumps(payload()).encode("utf-8")
    partial = full[:16]
    assert 0 < len(partial) < len(full)

    raw = [(k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in _auth_headers().items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/axle/evaluate",
        "raw_path": b"/api/v1/axle/evaluate",
        "query_string": b"",
        "root_path": "",
        "headers": raw,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    events = [
        {"type": "http.request", "body": partial, "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive():
        if events:
            return events.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        # Disconnected client need not receive a response; accept and drop.
        return None

    async def run():
        await remote_app.app(scope, receive, send)

    try:
        asyncio.run(asyncio.wait_for(run(), timeout=5))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Only a disconnect signal is acceptable without a response.
        # Anything else (including TimeoutError from the bound above)
        # must fail, not be suppressed.
        if type(exc).__name__ != "ClientDisconnect":
            raise

    assert _slots_free()
    ok_client = TestClient(remote_app.app, headers={"Authorization": "Bearer " + TOKEN})
    assert ok_client.post("/api/v1/axle/evaluate", json=payload()).status_code == 200
    assert _slots_free()


def test_stalled_body_reads_occupy_slots(remote_env, monkeypatch):
    monkeypatch.setattr(remote_app, "_body_timeout", _noop_body_timeout)
    now = [5000.0]
    monkeypatch.setattr(remote_app, "_clock", lambda: now[0])

    async def _main():
        release = asyncio.Event()
        entered_all = asyncio.Event()
        entered_count = 0
        original_read = remote_app._read_bounded

        async def _stalled_read(request):
            nonlocal entered_count
            entered_count += 1
            if entered_count == remote_app.MAX_CONCURRENT_EVALUATIONS:
                entered_all.set()
            await asyncio.wait_for(release.wait(), timeout=5)
            return await original_read(request)

        monkeypatch.setattr(remote_app, "_read_bounded", _stalled_read)
        small = json.dumps(payload()).encode("utf-8")
        t1 = asyncio.create_task(_asgi_request_async("POST", "/api/v1/axle/evaluate", small, _auth_headers()))
        t2 = asyncio.create_task(_asgi_request_async("POST", "/api/v1/axle/evaluate", small, _auth_headers()))
        await asyncio.wait_for(entered_all.wait(), timeout=5)
        assert not remote_app._EVAL_SLOTS.acquire(blocking=False)
        status3, headers3, body3 = await asyncio.wait_for(
            _asgi_request_async("POST", "/api/v1/axle/evaluate", small, _auth_headers()), timeout=5
        )
        assert status3 == 429
        assert json.loads(body3) == {"detail": "Too many concurrent evaluations"}
        assert headers3.get("cache-control") == "no-store"
        t1.cancel()
        try:
            await asyncio.wait_for(t1, timeout=5)
        except asyncio.CancelledError:
            pass
        assert remote_app._EVAL_SLOTS.acquire(blocking=False)
        remote_app._EVAL_SLOTS.release()
        release.set()
        status2, _, _ = await asyncio.wait_for(t2, timeout=5)
        assert status2 == 200
        assert _slots_free()
        status4, _, _ = await asyncio.wait_for(
            _asgi_request_async("POST", "/api/v1/axle/evaluate", small, _auth_headers()), timeout=5
        )
        assert status4 == 200

    asyncio.run(asyncio.wait_for(_main(), timeout=10))


def test_remote_source_isolation():
    # Direct-import check only; it does not prove transitive dependency isolation.
    src_path = pathlib.Path(remote_app.__file__)
    text = src_path.read_text()
    tree = ast.parse(text, filename=str(src_path))
    absolute_tops: set[str] = set()
    relative_modules: set[str] = set()
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute_tops.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                relative_modules.add(node.module or "")
                for alias in node.names:
                    imported_names.add(alias.name)
            else:
                if node.module:
                    absolute_tops.add(node.module.split(".")[0])
                for alias in node.names:
                    imported_names.add(alias.name)
    for bad in ["httpx", "requests", "urllib3", "aiohttp", "logging"]:
        assert bad not in absolute_tops
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "axle_hackathon" or alias.name.startswith("axle_hackathon."):
                    rest = alias.name.split(".")[1:]
                    assert rest == ["axle_api"], alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and (
                node.module == "axle_hackathon" or node.module.startswith("axle_hackathon.")
            ):
                rest = node.module.split(".")[1:]
                assert rest == ["axle_api"], node.module
    for mod in relative_modules:
        assert mod == "axle_api", mod
    assert "CORSMiddleware" not in imported_names
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            raise AssertionError("print() is not allowed in the remote boundary")
    for bad in ["MODEL_API_KEY", "AXLE_DEMO_TOKEN"]:
        assert bad not in text
    module_doc = ast.get_docstring(tree) or ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == module_doc:
                continue
            lowered = node.value.lower()
            assert "forwarded" not in lowered
            assert "x-real-ip" not in lowered
    for good in ["AxleEvaluationRequest", "AxleEvaluationResponse", "evaluate_for_client", "compare_digest"]:
        assert good in text
    assert isinstance(remote_app.MAX_BODY_BYTES, int) and remote_app.MAX_BODY_BYTES == 32768
    assert remote_app.BODY_READ_TIMEOUT_SECONDS == 10.0
    assert isinstance(remote_app._REQUEST_TIMES, collections.deque)
    assert remote_app._REQUEST_TIMES.maxlen == remote_app.RATE_LIMIT_MAX_REQUESTS
