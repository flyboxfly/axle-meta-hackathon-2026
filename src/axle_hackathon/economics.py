from decimal import Decimal, ROUND_HALF_UP
from .schemas import Equipment, Evaluation, Opportunity

# Deliberately synthetic and server-owned. No production profile access.
PROFILE_ID = "synthetic-box-001"
TARGET = Decimal("2.00")


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def evaluate(op: Opportunity, *, target: Decimal | None = TARGET,
             benchmark_source: str = "synthetic_default") -> Evaluation:
    miles = op.loaded_miles + op.deadhead_miles
    missing = [name for name in (
        "diesel_per_gallon", "mpg", "tolls", "driver_cost", "maintenance_per_mile",
        "equipment_trip_cost", "insurance_trip_allocation", "operating_hours", "schedule_feasible"
    ) if getattr(op, name) is None]
    if op.equipment != Equipment.BOX:
        missing.append("matching_equipment_carrier_profile")
    cost_fields = [op.diesel_per_gallon, op.mpg, op.tolls, op.driver_cost,
                   op.maintenance_per_mile, op.equipment_trip_cost, op.insurance_trip_allocation]
    cost = None
    if all(value is not None for value in cost_fields):
        cost = (miles / op.mpg * op.diesel_per_gallon + op.tolls + op.driver_cost
                + miles * op.maintenance_per_mile + op.equipment_trip_cost + op.insurance_trip_allocation)
    if target is None:
        missing.append("carrier_revenue_target")
    target_revenue = miles * target if target is not None else None
    gap = max(Decimal(0), target_revenue - op.payout) if target_revenue is not None else None
    # Missing facts always prevent an actionable acceptance/rejection classification.
    decision = "NEED_MORE_INFORMATION"
    if not missing:
        if op.schedule_feasible is False:
            decision = "DECLINE"
        elif op.payout < target_revenue or (cost is not None and op.payout <= cost):
            decision = "NEGOTIATE"
        else:
            decision = "ACCEPT"
    return Evaluation(
        profile_id=PROFILE_ID, decision=decision, total_miles=str(miles),
        loaded_rpm=money(op.payout / op.loaded_miles), all_mile_rpm=money(op.payout / miles),
        benchmark_source=benchmark_source,
        target_all_mile_rpm=money(target) if target is not None else None,
        target_revenue=money(target_revenue) if target_revenue is not None else None,
        revenue_gap_to_target=money(gap) if gap is not None else None, estimated_operating_cost=money(cost) if cost is not None else None,
        estimated_operating_surplus_after_allocated_costs=money(op.payout-cost) if cost is not None else None,
        missing_information=missing,
        assumptions=[f"Benchmark source: {benchmark_source}; revenue target is not a cost or profit target.",
                     "Payout is the complete confirmed total; no additional FSC or bid is inferred.",
                     "Mileage and schedule feasibility are supplied, not independently verified.",
                     "Equipment trip cost must include applicable per-mile rental fees without double counting.",
                     "ACCEPT means the supplied economic and schedule checks pass, not a booking or regulatory clearance."]
    )
