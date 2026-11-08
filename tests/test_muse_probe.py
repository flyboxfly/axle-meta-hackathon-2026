"""Offline credential-probe checks; credentials here are synthetic test values."""
import ast
import inspect

import pytest
from fastapi.testclient import TestClient

from axle_hackathon import remote_app
from test_h8_remote import remote_env, TOKEN

PATH = "/api/v1/axle/verify"


@pytest.mark.parametrize("headers,status,detail", [
    ({"Authorization": "Bearer " + TOKEN}, 200, None),
    ({}, 401, "Unauthorized"),
    ({"Authorization": "Bearer wrong-test-value"}, 401, "Unauthorized"),
    ({"Authorization": TOKEN}, 401, "Unauthorized"),
    ({"Authorization": "Bearer Bearer " + TOKEN}, 401, "Unauthorized"),
    ({"Authorization": "Bearer " + TOKEN, "Host": "other.test"}, 403, "Forbidden"),
    ({"Authorization": "Bearer " + TOKEN, "Origin": "https://testserver"}, 403, "Origin not allowed"),
    ({"Authorization": "Bearer " + TOKEN, "Origin": ""}, 403, "Origin not allowed"),
])
def test_probe_access(remote_env, headers, status, detail):
    with TestClient(remote_app.app) as client:
        response = client.get(PATH, headers=headers)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == ({"status": "ok", "synthetic_only": True} if status == 200 else {"detail": detail})
    assert (response.headers.get("www-authenticate") == "Bearer") == (status == 401)
    assert TOKEN not in response.text


def test_probe_does_not_evaluate_read_body_or_mutate_quota(remote_env, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("probe invoked evaluation/body/quota code")
    for name in ("evaluate_for_client", "_read_bounded", "_check_rate", "_eval_slot"):
        monkeypatch.setattr(remote_app, name, forbidden)
    remote_app._REQUEST_TIMES.extend([remote_app._clock()] * remote_app.RATE_LIMIT_MAX_REQUESTS)
    before = list(remote_app._REQUEST_TIMES)
    with TestClient(remote_app.app) as client:
        # Exhaust slots too: verification is independent of freight evaluation capacity.
        for _ in range(remote_app.MAX_CONCURRENT_EVALUATIONS):
            assert remote_app._EVAL_SLOTS.acquire(blocking=False)
        try:
            response = client.request("GET", PATH, headers={"Authorization": "Bearer " + TOKEN}, content=b"x" * 40000)
            assert response.status_code == 200
            assert not remote_app._EVAL_SLOTS.acquire(blocking=False)
        finally:
            for _ in range(remote_app.MAX_CONCURRENT_EVALUATIONS):
                remote_app._EVAL_SLOTS.release()
    assert list(remote_app._REQUEST_TIMES) == before
    # Restrict the route's call graph: no storage, outbound calls, tasks or calculator.
    calls = {ast.unparse(node.func) for node in ast.walk(ast.parse(inspect.getsource(remote_app.verify))) if isinstance(node, ast.Call)}
    assert calls == {"_load_or_500", "_check_host", "_check_origin_absent", "_check_auth", "JSONResponse", "app.get"}


def test_probe_configuration_failure_and_method(remote_env, monkeypatch):
    with TestClient(remote_app.app) as client:
        assert client.post(PATH).status_code == 405
        monkeypatch.delenv("AXLE_API_TOKEN")
        response = client.get(PATH)
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal error"}
        assert response.headers["cache-control"] == "no-store"
