"""H7 local external-client contract. No native connector or remote boundary."""
from decimal import Decimal
from typing import Literal
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from .economics import evaluate
from .schemas import Evaluation, Opportunity


class ConfirmedBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    target_all_mile_rpm: Decimal | None = Field(gt=0, le=100, decimal_places=2)
    confirmed: StrictBool

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirmed:
            raise ValueError("Confirm the carrier's target choice, including unknown")
        return self


class AxleEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opportunity: Opportunity
    benchmark: ConfirmedBenchmark
    facts_confirmed: StrictBool
    source: Literal["manual", "screenshot"]

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.facts_confirmed:
            raise ValueError("Carrier review of supplied facts is required")
        return self


class NextQuestion(BaseModel):
    field: str
    question: str


class AxleEvaluationResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["evaluated"] = "evaluated"
    evaluation: Evaluation
    next_questions: list[NextQuestion]
    source: Literal["manual", "screenshot"]
    confirmation_basis: Literal["caller_assertion"] = "caller_assertion"
    delivery: Literal["canonical_api"] = "canonical_api"
    model_invoked: Literal[False] = False
    native_connector: Literal[False] = False


QUESTIONS = {
    "diesel_per_gallon": "What diesel price per gallon applies to this trip?",
    "mpg": "What fuel economy in miles per gallon applies to this equipment?",
    "tolls": "What are the total trip tolls?",
    "driver_cost": "What is the total driver cost for this trip?",
    "maintenance_per_mile": "What maintenance allocation per mile applies?",
    "equipment_trip_cost": "What equipment cost applies, including rental mileage fees once?",
    "insurance_trip_allocation": "What insurance cost is allocated to this trip?",
    "operating_hours": "How many operating hours does the trip require?",
    "schedule_feasible": "Have you confirmed that you can complete this trip within your schedule?",
    "matching_equipment_carrier_profile": "This prototype supports only a synthetic 26-foot box-truck profile; a matching profile is unavailable for this equipment.",
    "carrier_revenue_target": "What all-mile revenue target do you confirm for this evaluation?",
}


def local_api_access(request: Request):
    # Keep the new interface local until a separately reviewed remote boundary exists.
    if request.url.hostname not in {"127.0.0.1", "localhost", "testserver"} or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Local API preview only")
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Same-origin access required")


def evaluate_for_client(body: AxleEvaluationRequest) -> AxleEvaluationResponse:
    target = body.benchmark.target_all_mile_rpm
    result = evaluate(body.opportunity, target=target,
                      benchmark_source="carrier_unknown" if target is None else "carrier_confirmed")
    return AxleEvaluationResponse(evaluation=result, source=body.source,
        next_questions=[NextQuestion(field=key, question=QUESTIONS[key]) for key in result.missing_information])
