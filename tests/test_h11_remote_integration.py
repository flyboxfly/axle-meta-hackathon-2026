"""Offline Meta selection → HTTPS-shaped adapter → isolated API handler tests."""
import json
from pathlib import Path
import runpy

import httpx
import pytest
from fastapi.testclient import TestClient

from axle_hackathon import remote_client as remote, remote_app, web
from axle_hackathon.axle_api import evaluate_for_client
from axle_hackathon.external_agent import synthetic_request
from test_h2 import browser
from test_h5 import install_client, payload, response_with, tool_call


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("AXLE_BROWSER_EVALUATOR", "remote")
    monkeypatch.setenv("AXLE_REMOTE_BASE_URL", remote.DEMO_BASE_URL)
    monkeypatch.setenv("AXLE_REMOTE_API_TOKEN", "PRIVATE_REMOTE_TOKEN")
    monkeypatch.setenv("AXLE_API_TOKEN", "PRIVATE_REMOTE_TOKEN")
    monkeypatch.setenv("AXLE_API_ALLOWED_HOSTS", "axle-api-demo.flyboxfly.com")
    remote_app._REQUEST_TIMES.clear()


def install_http(monkeypatch, handler):
    original = httpx.Client
    calls = []
    def capture(request):
        calls.append(request)
        return handler(request)
    def factory(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["verify"] is True
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"].connect == 5
        assert kwargs["timeout"].read == 10
        return original(**kwargs, transport=httpx.MockTransport(capture))
    monkeypatch.setattr(remote.httpx, "Client", factory)
    return calls


def success(request):
    return httpx.Response(200, json=evaluate_for_client(synthetic_request()).model_dump(mode="json"),
                          headers={"Cache-Control": "no-store"})


@pytest.mark.parametrize("target,decision,gap", [
    ("2.00", "NEGOTIATE", "60.00"), ("1.75", "ACCEPT", "0.00"),
    (None, "NEED_MORE_INFORMATION", None)])
def test_browser_remote_uses_actual_isolated_handler(browser, configured, monkeypatch, target, decision, gap):
    server = TestClient(remote_app.app, base_url=remote.DEMO_BASE_URL)
    def handler(request):
        assert str(request.url) == remote.DEMO_BASE_URL + "/api/v1/axle/evaluate"
        assert request.headers["authorization"] == "Bearer PRIVATE_REMOTE_TOKEN"
        assert "origin" not in request.headers
        assert "PRIVATE_" not in request.content.decode()
        reply = server.post(request.url.path, content=request.content, headers=dict(request.headers))
        return httpx.Response(reply.status_code, content=reply.content, headers=reply.headers)
    calls = install_http(monkeypatch, handler)
    model_calls = install_client(monkeypatch, lambda *a: response_with(tool_call()))
    monkeypatch.setattr(web, "evaluate", lambda *a, **k: pytest.fail("Local fallback"))
    reply = browser.post("/api/v1/browser/evaluate", json=payload(target, facts_confirmed=True))
    assert reply.status_code == 200
    body = reply.json()
    assert body["evaluation"]["decision"] == decision
    assert body["evaluation"]["revenue_gap_to_target"] == gap
    assert body["evaluation"]["estimated_operating_cost"] == "290.00"
    assert body["evaluation"]["estimated_operating_surplus_after_allocated_costs"] == "130.00"
    assert body["canonical_api_result"]["source"] == "screenshot"
    assert body["trace"][0]["transport"] == "remote_https"
    assert body["trace"][0]["model_received_result"] is False
    assert len(calls) == len(model_calls) == 1
    assert "PRIVATE_REMOTE_TOKEN" not in reply.text + json.dumps(model_calls)
    assert "PRIVATE_KEY" not in reply.text + json.dumps(model_calls)


@pytest.mark.parametrize("updates", [{"facts_confirmed": False}, {"benchmark": None},
                                     {"screenshot_confirmed": False}])
def test_remote_confirmation_precedes_model(browser, configured, monkeypatch, updates):
    model = install_client(monkeypatch, lambda *a: pytest.fail("Unconfirmed facts reached Meta"))
    reply = browser.post("/api/v1/browser/evaluate", json=payload(facts_confirmed=True, **updates) if "facts_confirmed" not in updates else payload(**updates))
    assert reply.status_code == 422 and not model


@pytest.mark.parametrize("env,value", [("AXLE_REMOTE_API_TOKEN", ""),
    ("AXLE_REMOTE_BASE_URL", "https://attacker.test"), ("AXLE_BROWSER_EVALUATOR", "typo")])
def test_bad_config_precedes_model(browser, configured, monkeypatch, env, value, caplog):
    monkeypatch.setenv(env, value)
    model = install_client(monkeypatch, lambda *a: pytest.fail("Invalid config reached Meta"))
    reply = browser.post("/api/v1/browser/evaluate", json=payload(facts_confirmed=True))
    assert reply.status_code == 503 and not model
    assert "PRIVATE_" not in reply.text + caplog.text


def test_changed_model_facts_prevent_remote_call(browser, configured, monkeypatch):
    calls = install_http(monkeypatch, lambda *a: pytest.fail("Altered facts reached API"))
    install_client(monkeypatch, lambda *a: response_with(tool_call(arguments=json.dumps({"equipment":"box_truck_26ft", "payout":"999", "loaded_miles":"180", "deadhead_miles":"60"}))))
    assert browser.post("/api/v1/browser/evaluate", json=payload(facts_confirmed=True)).status_code == 502
    assert not calls


@pytest.mark.parametrize("kind", ["timeout", "connection", "redirect", "auth", "rate", "invalid_json", "oversize", "bad_provenance", "missing_field", "false_synthetic", "changed_target", "html", "cache"])
def test_failure_never_falls_back_or_leaks(browser, configured, monkeypatch, caplog, kind):
    def handler(request):
        if kind == "timeout": raise httpx.ReadTimeout("PRIVATE_FAILURE", request=request)
        if kind == "connection": raise httpx.ConnectError("PRIVATE_FAILURE", request=request)
        if kind in {"redirect", "auth", "rate"}:
            return httpx.Response({"redirect":307,"auth":401,"rate":429}[kind],
                text="PRIVATE_FAILURE", headers={"Location":"https://attacker.test"})
        headers = {"Cache-Control":"no-store"}
        if kind == "invalid_json": return httpx.Response(200, content=b"PRIVATE_INVALID", headers={**headers,"Content-Type":"application/json"})
        if kind == "oversize": return httpx.Response(200, content=b"x" * 70000, headers={**headers,"Content-Type":"application/json"})
        if kind == "html": return httpx.Response(200, text="PRIVATE_HTML", headers=headers)
        raw = evaluate_for_client(synthetic_request()).model_dump(mode="json")
        raw["source"] = "screenshot"
        if kind == "bad_provenance": raw["model_invoked"] = True
        if kind == "missing_field": del raw["evaluation"]["synthetic"]
        if kind == "false_synthetic": raw["evaluation"]["synthetic"] = False
        if kind == "changed_target": raw["evaluation"]["target_all_mile_rpm"] = "0.01"
        if kind == "cache": headers = {}
        return httpx.Response(200, json=raw, headers=headers)
    calls = install_http(monkeypatch, handler)
    install_client(monkeypatch, lambda *a: response_with(tool_call()))
    monkeypatch.setattr(web, "evaluate", lambda *a, **k: pytest.fail("Local fallback"))
    reply = browser.post("/api/v1/browser/evaluate", json=payload("2.00", facts_confirmed=True))
    assert reply.status_code == 502
    assert "evaluation" not in reply.json()
    assert len(calls) == 1
    assert "PRIVATE_" not in reply.text + caplog.text
    assert not web._gate.locked()


def test_local_mode_unchanged(browser, monkeypatch):
    monkeypatch.delenv("AXLE_BROWSER_EVALUATOR", raising=False)
    monkeypatch.setattr(web, "evaluate_remote", lambda *a: pytest.fail("Unexpected remote call"))
    install_client(monkeypatch, lambda *a: response_with(tool_call()))
    reply = browser.post("/api/v1/browser/evaluate", json=payload("2.00"))
    assert reply.status_code == 200
    assert reply.json()["trace"][0]["transport"] == "in_process"


def test_confirmation_rejects_coerced_values(browser, configured):
    for field in ("facts_confirmed", "benchmark"):
        data = payload(facts_confirmed=True)
        if field == "benchmark": data[field]["confirmed"] = 1
        else: data[field] = "true"
        assert browser.post("/api/v1/browser/evaluate", json=data).status_code == 422


def test_static_contract_tracks_models_and_only_remote_routes():
    root = Path(__file__).resolve().parents[1]
    generated = runpy.run_path(str(root / "scripts/export_reviewer_openapi.py"))["document"]()
    stored = json.loads((root / "docs/connector/openapi.json").read_text())
    assert generated == stored
    assert set(stored["paths"]) == {"/api/health", "/api/v1/axle/evaluate"}
    operation = stored["paths"]["/api/v1/axle/evaluate"]["post"]
    example = operation["requestBody"]["content"]["application/json"]["example"]
    assert evaluate_for_client(synthetic_request()).model_dump(mode="json") == operation["responses"]["200"]["content"]["application/json"]["example"]
    assert example["facts_confirmed"] is True
    assert operation["security"] == [{"bearerAuth": []}]
