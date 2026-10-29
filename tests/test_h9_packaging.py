"""H9 offline packaging validation (review candidate).

Exercises the staged minimal runtime closure (the five modules Dockerfile.remote
copies) in a subprocess isolated from the full source tree, using disposable
test configuration and raw ASGI calls (no TestClient/httpx in the probe).

These checks do NOT establish container isolation, dependency-installation
success, or network-egress isolation. They verify file grounding, stdlib-only
health-probe behavior, import closure, and canonical economics of the staged
files only. Container, install, and egress claims require the owner-run steps
in docs/H9_DEPLOYMENT.md, none of which have been executed here.
"""

import ast
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
from unittest import mock

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REMOTE_LOCK = REPO_ROOT / "requirements.remote.lock.txt"
FULL_LOCK = REPO_ROOT / "requirements.lock.txt"
HEALTHCHECK = REPO_ROOT / "deploy" / "remote_healthcheck.py"
SRC_DIR = REPO_ROOT / "src" / "axle_hackathon"

# The five runtime modules staged into the image. This list documents the
# intended closure for the subprocess test; it is not parsed from Dockerfile
# text (see module docstring on brittle restatements).
STAGED_MODULES = (
    "__init__.py",
    "remote_app.py",
    "axle_api.py",
    "schemas.py",
    "economics.py",
)

FORBIDDEN_APP_MODULES = (
    "axle_hackathon.app",
    "axle_hackathon.web",
    "axle_hackathon.meta_agent",
    "axle_hackathon.vision",
    "axle_hackathon.external_agent",
)

# Inference/image/client/test SDKs that the remote boundary must not import.
FORBIDDEN_SDK_TOPS = frozenset(
    {
        "openai",
        "httpx",
        "httpx2",
        "httpcore",
        "httpcore2",
        "pil",
        "pytest",
        "requests",
        "aiohttp",
        "urllib3",
    }
)

# Packages that must be absent from the remote candidate lock (normalized:
# lowercase, "_" and "." treated as "-").
FORBIDDEN_LOCK_NAMES = frozenset(
    {
        "openai",
        "httpx",
        "httpx2",
        "httpcore",
        "httpcore2",
        "pillow",
        "pytest",
        "iniconfig",
        "pluggy",
        "pygments",
        "packaging",
        "socksio",
        "jiter",
        "certifi",
        "truststore",
    }
)

# Packages the remote closure requires (normalized as above).
REQUIRED_LOCK_NAMES = frozenset(
    {
        "annotated-doc",
        "annotated-types",
        "anyio",
        "click",
        "fastapi",
        "h11",
        "idna",
        "opentelemetry-api",
        "pydantic",
        "pydantic-core",
        "sniffio",
        "starlette",
        "typing-inspection",
        "typing-extensions",
        "uvicorn",
    }
)

DISPOSABLE_TOKEN = "h9-disposable-packaging-token"
DISPOSABLE_HOST = "h9-packaging.test"


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(".", "-")


def _pins(path: pathlib.Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        assert "==" in stripped, f"{path.name}: pin must use '==': {stripped!r}"
        name, version = (part.strip() for part in stripped.split("==", 1))
        assert name and version, f"{path.name}: malformed pin: {stripped!r}"
        assert ";" not in version and "," not in version and " " not in version, (
            f"{path.name}: pin must be an exact version: {stripped!r}"
        )
        pins[_normalize(name)] = version
    return pins


def test_remote_candidate_lock_grounded_and_minimal():
    text = REMOTE_LOCK.read_text()
    lowered = text.lower()
    assert "candidate" in lowered and "pending" in lowered
    assert "--hash" not in text and "sha256" not in lowered
    remote = _pins(REMOTE_LOCK)
    full = _pins(FULL_LOCK)
    assert remote, "remote candidate lock has no pins"
    for name, version in remote.items():
        assert name in full, f"{name} not grounded in requirements.lock.txt"
        assert full[name] == version, f"{name} version differs from lock"
    assert REQUIRED_LOCK_NAMES <= set(remote)
    assert not (FORBIDDEN_LOCK_NAMES & set(remote))


def _load_healthcheck_module():
    spec = importlib.util.spec_from_file_location(
        "h9_remote_healthcheck", HEALTHCHECK
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_healthcheck_probe_is_stdlib_only():
    tree = ast.parse(HEALTHCHECK.read_text(), filename=str(HEALTHCHECK))
    tops: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                tops.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                tops.add(node.module.split(".")[0])
    assert tops <= {"__future__", "http", "json", "os", "sys"}, tops
    assert not (FORBIDDEN_SDK_TOPS & {t.lower() for t in tops})


def test_healthcheck_host_selection(monkeypatch):
    module = _load_healthcheck_module()
    timeout = module._TIMEOUT_SECONDS
    assert isinstance(timeout, (int, float)) and 1 <= timeout <= 10
    assert module._CONNECT_HOST == "127.0.0.1"
    assert module._HEALTH_PATH == "/api/health"
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", DISPOSABLE_HOST)
    assert module._select_host() == DISPOSABLE_HOST
    monkeypatch.setenv(
        "AXLE_API_ALLOWED_HOSTS", "First.Test,second.test"
    )
    assert module._select_host() == "first.test"
    for bad in ["", "   ", "*,allowed.test", "allowed.test,*"]:
        monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", bad)
        with pytest.raises(ValueError):
            module._select_host()
    monkeypatch.delenv("AXLE_API_ALLOWED_HOSTS", raising=False)
    with pytest.raises(ValueError):
        module._select_host()


def _mock_health_connection(monkeypatch, module, *, status=200,
                             body=b'{"status": "ok", "synthetic_only": true}',
                             read_exc=None):
    """Install a mocked HTTPConnection returning one canned response."""
    import http.client as http_client

    response = mock.MagicMock()
    response.status = status
    if read_exc is not None:
        response.read.side_effect = read_exc
    else:
        response.read.return_value = body
    conn = mock.MagicMock()
    conn.getresponse.return_value = response
    ctor = mock.MagicMock(return_value=conn)
    monkeypatch.setattr(http_client, "HTTPConnection", ctor)
    return ctor, conn, response


def test_healthcheck_main_valid_returns_zero_and_closes(monkeypatch):
    module = _load_healthcheck_module()
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", DISPOSABLE_HOST)
    ctor, conn, _ = _mock_health_connection(monkeypatch, module)
    assert module.main() == 0
    ctor.assert_called_once_with(
        "127.0.0.1", 8000, timeout=module._TIMEOUT_SECONDS
    )
    conn.request.assert_called_once()
    args, kwargs = conn.request.call_args
    assert args[:2] == ("GET", "/api/health")
    assert kwargs["headers"]["Host"] == DISPOSABLE_HOST
    conn.close.assert_called_once()


@pytest.mark.parametrize(
    "kind", ["non-200", "malformed", "wrong-flag", "oversized"]
)
def test_healthcheck_main_response_failures_return_one_and_close(
    monkeypatch, kind
):
    module = _load_healthcheck_module()
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", DISPOSABLE_HOST)
    if kind == "non-200":
        status, body = 500, b'{"status": "ok", "synthetic_only": true}'
    elif kind == "malformed":
        status, body = 200, b"not json"
    elif kind == "wrong-flag":
        status, body = 200, b'{"status": "ok", "synthetic_only": false}'
    else:
        status, body = 200, b"x" * (module._MAX_BODY_BYTES + 1)
    _, conn, _ = _mock_health_connection(
        monkeypatch, module, status=status, body=body
    )
    assert module.main() == 1
    conn.close.assert_called_once()


def test_healthcheck_main_connection_failure_returns_one(monkeypatch):
    import http.client as http_client

    module = _load_healthcheck_module()
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", DISPOSABLE_HOST)
    monkeypatch.setattr(
        http_client,
        "HTTPConnection",
        mock.MagicMock(side_effect=OSError("refused")),
    )
    assert module.main() == 1


def test_healthcheck_main_read_failure_closes_connection(monkeypatch):
    module = _load_healthcheck_module()
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", DISPOSABLE_HOST)
    _, conn, _ = _mock_health_connection(
        monkeypatch, module, read_exc=OSError("read failed")
    )
    assert module.main() == 1
    conn.close.assert_called_once()


def test_healthcheck_main_sends_explicit_allowed_host(monkeypatch):
    module = _load_healthcheck_module()
    monkeypatch.setenv(
        "AXLE_API_ALLOWED_HOSTS", "First.Test,second.test"
    )
    _, conn, _ = _mock_health_connection(monkeypatch, module)
    assert module.main() == 0
    _, kwargs = conn.request.call_args
    assert kwargs["headers"]["Host"] == "first.test"
    conn.close.assert_called_once()


_PROBE = r'''
"""Isolated H9 probe. Runs with PYTHONPATH limited to the staged tree."""
import asyncio
import json
import os
import sys

STAGED = os.environ["H9_STAGED_SRC"]
TOKEN = os.environ["AXLE_API_TOKEN"]
HOST = os.environ["AXLE_API_ALLOWED_HOSTS"]
assert TOKEN and HOST and "," not in HOST, "probe needs single disposable host"

import axle_hackathon.remote_app as ra

real = os.path.realpath(ra.__file__)
expected = os.path.realpath(os.path.join(STAGED, "axle_hackathon", "remote_app.py"))
assert real == expected, f"loaded {real}, expected {expected}"

FORBIDDEN_APP = [
    "axle_hackathon.app",
    "axle_hackathon.web",
    "axle_hackathon.meta_agent",
    "axle_hackathon.vision",
    "axle_hackathon.external_agent",
]
FORBIDDEN_SDK = {
    "openai", "httpx", "httpx2", "httpcore", "httpcore2",
    "pil", "pytest", "requests", "aiohttp", "urllib3",
}


def assert_clean_imports(stage):
    loaded_tops = {name.split(".")[0].lower() for name in sys.modules}
    bad_sdk = FORBIDDEN_SDK & loaded_tops
    assert not bad_sdk, f"{stage}: sdk imports {sorted(bad_sdk)}"
    bad_app = [m for m in FORBIDDEN_APP if m in sys.modules]
    assert not bad_app, f"{stage}: app imports {bad_app}"


assert_clean_imports("import")
for mod in FORBIDDEN_APP:
    try:
        __import__(mod)
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError(f"{mod} unexpectedly importable from staged tree")

COMPLETE = {
    "equipment": "box_truck_26ft", "payout": "420",
    "loaded_miles": "180", "deadhead_miles": "60",
    "diesel_per_gallon": "4", "mpg": "10", "tolls": "20",
    "driver_cost": "80", "maintenance_per_mile": "0.10",
    "equipment_trip_cost": "50", "insurance_trip_allocation": "20",
    "operating_hours": "6", "schedule_feasible": True,
}


async def call(method, path, body: bytes, headers: dict):
    raw = [(k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in headers.items()]
    scope = {
        "type": "http", "http_version": "1.1", "method": method,
        "scheme": "http", "path": path, "raw_path": path.encode("utf-8"),
        "query_string": b"", "root_path": "", "headers": raw,
        "client": ("testclient", 50000), "server": ("testserver", 80),
    }
    chunks = [body[i:i + 8192] for i in range(0, len(body), 8192)] or [b""]
    queue = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]

    async def receive():
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    messages = []

    async def send(message):
        messages.append(message)

    await ra.app(scope, receive, send)
    status = None
    resp_headers = {}
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


async def main():
    base = {"host": HOST, "authorization": "Bearer " + TOKEN,
            "content-type": "application/json"}
    status, headers, body = await call("GET", "/api/health", b"", {"host": HOST})
    assert status == 200, body[:200]
    assert headers.get("cache-control") == "no-store"
    assert json.loads(body) == {"status": "ok", "synthetic_only": True}

    status, _, _ = await call("GET", "/docs", b"", {"host": HOST})
    assert status == 404
    no_auth = {"host": HOST, "content-type": "application/json"}
    payload = {"opportunity": COMPLETE,
               "benchmark": {"target_all_mile_rpm": "2.00", "confirmed": True},
               "facts_confirmed": True, "source": "screenshot"}
    status, headers, body = await call(
        "POST", "/api/v1/axle/evaluate", json.dumps(payload).encode("utf-8"), no_auth)
    assert status == 401, body[:200]
    assert headers.get("www-authenticate") == "Bearer"

    decisions = []
    gaps = []
    for target in ["2.00", "1.75", None]:
        payload["benchmark"] = {"target_all_mile_rpm": target, "confirmed": True}
        status, headers, body = await call(
            "POST", "/api/v1/axle/evaluate", json.dumps(payload).encode("utf-8"), base)
        assert status == 200, body[:300]
        assert headers.get("cache-control") == "no-store"
        data = json.loads(body)
        ev = data["evaluation"]
        decisions.append(ev["decision"])
        gaps.append(ev["revenue_gap_to_target"])
        assert ev["estimated_operating_cost"] == "290.00", ev
        assert ev["estimated_operating_surplus_after_allocated_costs"] == "130.00", ev
        assert ev["synthetic"] is True and ev["profile_id"] == "synthetic-box-001"
        assert data["schema_version"] == "1.0"
        assert data["confirmation_basis"] == "caller_assertion"
        assert data["delivery"] == "canonical_api"
        assert data["model_invoked"] is False
        assert data["native_connector"] is False
    assert decisions == ["NEGOTIATE", "ACCEPT", "NEED_MORE_INFORMATION"], decisions
    assert gaps == ["60.00", "0.00", None], gaps
    return {"decisions": decisions, "gaps": gaps}


result = asyncio.run(asyncio.wait_for(main(), timeout=30))
assert_clean_imports("after-requests")
print(json.dumps({"ok": True, "result": result}))
'''


def test_staged_runtime_closure_in_isolated_subprocess(tmp_path):
    staged_src = tmp_path / "staged" / "src"
    staged_pkg = staged_src / "axle_hackathon"
    staged_pkg.mkdir(parents=True)
    for name in STAGED_MODULES:
        data = (SRC_DIR / name).read_bytes()
        (staged_pkg / name).write_bytes(data)
    assert {p.name for p in staged_pkg.iterdir()} == set(STAGED_MODULES)

    probe_path = tmp_path / "probe_h9.py"
    probe_path.write_text(_PROBE)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(staged_src)
    env["H9_STAGED_SRC"] = str(staged_src)
    env["AXLE_API_TOKEN"] = DISPOSABLE_TOKEN
    env["AXLE_API_ALLOWED_HOSTS"] = DISPOSABLE_HOST
    env.pop("MODEL_API_KEY", None)
    env["AXLE_DEMO_TOKEN"] = "local-only-token"

    proc = subprocess.run(
        [sys.executable, str(probe_path)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert DISPOSABLE_TOKEN not in proc.stdout
    assert DISPOSABLE_TOKEN not in proc.stderr
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, "probe produced no output"
    report = json.loads(lines[-1])
    assert report["ok"] is True
    assert report["result"]["decisions"] == [
        "NEGOTIATE",
        "ACCEPT",
        "NEED_MORE_INFORMATION",
    ]
    assert report["result"]["gaps"] == ["60.00", "0.00", None]
