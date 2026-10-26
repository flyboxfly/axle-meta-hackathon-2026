from decimal import Decimal
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class Equipment(StrEnum):
    BOX = "box_truck_26ft"
    VAN = "cargo_sprinter_van"
    TRACTOR = "tractor_carrier_owned_trailer"
    POWER_ONLY = "power_only_amazon_provided_trailer"


class Opportunity(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    equipment: Equipment
    payout: Decimal = Field(ge=0, le=1000000, description="Complete confirmed payout; do not add bid or FSC again.")
    loaded_miles: Decimal = Field(gt=0, le=100000)
    deadhead_miles: Decimal = Field(ge=0, le=100000, description="All additional miles committed to this opportunity, including known repositioning.")
    diesel_per_gallon: Decimal | None = Field(default=None, gt=0, le=100)
    mpg: Decimal | None = Field(default=None, gt=0, le=100)
    tolls: Decimal | None = Field(default=None, ge=0, le=100000)
    driver_cost: Decimal | None = Field(default=None, ge=0, le=100000)
    maintenance_per_mile: Decimal | None = Field(default=None, ge=0, le=100)
    equipment_trip_cost: Decimal | None = Field(default=None, ge=0, le=100000)
    insurance_trip_allocation: Decimal | None = Field(default=None, ge=0, le=100000)
    operating_hours: Decimal | None = Field(default=None, gt=0, le=1000)
    schedule_feasible: bool | None = None


class Evaluation(BaseModel):
    synthetic: bool = True
    profile_id: str
    decision: str
    total_miles: str
    loaded_rpm: str
    all_mile_rpm: str
    target_all_mile_rpm: str
    target_revenue: str
    revenue_gap_to_target: str
    estimated_operating_cost: str | None
    estimated_operating_surplus_after_allocated_costs: str | None
    missing_information: list[str]
    assumptions: list[str]


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=8000)
