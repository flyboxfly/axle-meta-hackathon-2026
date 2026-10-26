import json
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from axle_hackathon.app import app
from axle_hackathon.economics import evaluate
from axle_hackathon.meta_agent import delegate
from axle_hackathon.schemas import Opportunity

BASE = dict(equipment="box_truck_26ft", payout="420", loaded_miles="180", deadhead_miles="60")
COMPLETE = dict(BASE, diesel_per_gallon="4", mpg="10", tolls="20", driver_cost="80",
                maintenance_per_mile="0.10", equipment_trip_cost="50",
                insurance_trip_allocation="20", operating_hours="6", schedule_feasible=True)


def test_rpm_and_missing_facts():
    result = evaluate(Opportunity(**BASE))
    assert (result.loaded_rpm, result.all_mile_rpm, result.target_revenue, result.revenue_gap_to_target) == ("2.33", "1.75", "480.00", "60.00")
    assert result.decision == "NEED_MORE_INFORMATION"
    assert result.estimated_operating_cost is None


def test_full_costs_and_negotiation():
    result = evaluate(Opportunity(**COMPLETE))
    assert result.estimated_operating_cost == "290.00"
    assert result.estimated_operating_surplus_after_allocated_costs == "130.00"
    assert result.decision == "NEGOTIATE"


@pytest.mark.parametrize("updates,decision", [({"payout":"500"}, "ACCEPT"),
    ({"payout":"500", "schedule_feasible":False}, "DECLINE"),
    ({"payout":"500", "equipment_trip_cost":"400"}, "NEGOTIATE"),
    ({"equipment":"power_only_amazon_provided_trailer"}, "NEED_MORE_INFORMATION")])
def test_decision_gates(updates, decision):
    assert evaluate(Opportunity(**dict(COMPLETE, **updates))).decision == decision


@pytest.mark.parametrize("updates", [{"loaded_miles":0}, {"deadhead_miles":-1},
    {"payout":"NaN"}, {"mpg":0}, {"bid":100}, {"carrier_id":"another-carrier"}])
def test_invalid_or_untrusted_input(updates):
    with pytest.raises(ValidationError):
        Opportunity(**dict(BASE, **updates))


def test_api_auth_and_output(monkeypatch):
    client = TestClient(app)
    monkeypatch.delenv("AXLE_DEMO_TOKEN", raising=False)
    assert client.post("/api/v1/freight/evaluate", json=BASE).status_code == 503
    monkeypatch.setenv("AXLE_DEMO_TOKEN", "test-only")
    assert client.post("/api/v1/freight/evaluate", json=BASE).status_code == 401
    response = client.post("/api/v1/freight/evaluate", json=BASE, headers={"Authorization":"Bearer test-only"})
    assert response.status_code == 200
    assert response.json()["all_mile_rpm"] == "1.75"
    assert client.get("/openapi.json").status_code == 200


def test_delegation_protocol_offline(monkeypatch):
    """Protocol test with fake model transport and real in-process HTTP; NOT live model proof."""
    monkeypatch.setenv("AXLE_DEMO_TOKEN", "test-only")
    http = TestClient(app)
    calls = []
    def execute(op):
        response = http.post("/api/v1/freight/evaluate", json=op.model_dump(mode="json"),
                             headers={"Authorization":"Bearer test-only"})
        response.raise_for_status()
        return response.json()
    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return NS(id="fake-first", output=[NS(type="function_call", name="evaluate_freight_opportunity",
                arguments=json.dumps(BASE), call_id="fake-call")])
        assert kwargs["previous_response_id"] == "fake-first"
        assert kwargs["input"][0]["call_id"] == "fake-call"
        assert json.loads(kwargs["input"][0]["output"])["all_mile_rpm"] == "1.75"
        return NS(id="fake-final", output=[], output_text="Synthetic result", usage=None)
    result = delegate(NS(responses=NS(create=create)), "evaluate", execute)
    assert len(result["trace"]) == 1
    assert result["evaluations"][0]["decision"] == "NEED_MORE_INFORMATION"


def test_model_without_delegation_fails():
    client = NS(responses=NS(create=lambda **kw: NS(output=[])))
    with pytest.raises(RuntimeError, match="did not delegate"):
        delegate(client, "evaluate", lambda op: None)


def test_installed_sdk_initializes_without_network():
    from openai import OpenAI
    client = OpenAI(api_key="offline-placeholder", base_url="https://api.meta.ai/v1")
    try:
        assert callable(client.responses.create)
    finally:
        client.close()
