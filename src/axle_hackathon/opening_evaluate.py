"""Deterministic offer/counteroffer evaluation. Pure Decimal arithmetic.

Point-in-time economics only: posted or owner-entered compensation against
CPM-based operating cost, revenue target and minimum charge, plus a
carrier-confirmed feasibility gate. No routing, HOS verification, schedule
validation, stop modeling or market data. Unknowns never default.
"""
from decimal import Decimal

from .economics import money
from .pilot import Frozen


class OfferInputs(Frozen):
    revision: int
    compensation: Decimal
    compensation_source: str
    loaded_miles: Decimal | None = None
    deadhead_miles: Decimal | None = None
    reposition_miles: Decimal | None = None
    operating_cpm: Decimal | None = None
    target_all_mile_rpm: Decimal | None = None
    minimum_job_charge: Decimal | None = None
    schedule_feasible: bool | None = None
    pricing_source: str = 'carrier supplied'


def evaluate_offer(data: OfferInputs) -> dict:
    """ACCEPT, NEGOTIATE, DECLINE or NEED_MORE_INFORMATION with checkable figures."""
    if data.revision < 1:
        raise ValueError('Positive revision required')
    if data.compensation_source not in ('posted offer', 'owner counteroffer'):
        raise ValueError('Explicit compensation source required')
    if data.compensation < 0 or data.compensation > 1000000:
        raise ValueError('Bounded compensation required')
    missing = []
    if data.loaded_miles is None:
        missing.append('loaded_miles')
    if data.operating_cpm is None:
        missing.append('operating_cpm')
    if data.target_all_mile_rpm is None:
        missing.append('carrier_revenue_target')
    if data.minimum_job_charge is None:
        missing.append('minimum_job_charge')
    if data.schedule_feasible is None:
        missing.append('schedule_feasibility')
    miles = None
    if data.loaded_miles is not None:
        miles = data.loaded_miles + (data.deadhead_miles or 0) + (data.reposition_miles or 0)
    # Single CPM cost term; segments counted once; minimum compared, never added.
    cost = miles * data.operating_cpm if miles is not None and data.operating_cpm is not None else None
    target_revenue = miles * data.target_all_mile_rpm if miles is not None and data.target_all_mile_rpm is not None else None
    gap = max(Decimal(0), target_revenue - data.compensation) if target_revenue is not None else None
    surplus = data.compensation - cost if cost is not None else None
    decision = 'NEED_MORE_INFORMATION'
    if not missing:
        if data.schedule_feasible is False:
            decision = 'DECLINE'
        elif (data.compensation < target_revenue or data.compensation <= cost
                or data.compensation < data.minimum_job_charge):
            decision = 'NEGOTIATE'
        else:
            decision = 'ACCEPT'
    return dict(
        revision=data.revision, decision=decision,
        compensation=money(data.compensation), compensation_source=data.compensation_source,
        total_miles=str(miles) if miles is not None else None,
        loaded_rpm=money(data.compensation / data.loaded_miles) if data.loaded_miles else None,
        all_mile_rpm=money(data.compensation / miles) if miles else None,
        estimated_operating_cost=money(cost) if cost is not None else None,
        target_revenue=money(target_revenue) if target_revenue is not None else None,
        revenue_gap_to_target=money(gap) if gap is not None else None,
        estimated_operating_surplus=money(surplus) if surplus is not None else None,
        missing_information=missing,
        benchmark_source='carrier_confirmed' if data.target_all_mile_rpm is not None else 'carrier_unknown',
        pricing_source=data.pricing_source,
        assumptions=[
            'Compensation is the confirmed posted offer or owner counteroffer; nothing is added.',
            'Operating cost is total confirmed miles times all-operating-expense CPM, counted once.',
            'Mileage, availability and schedule feasibility are carrier-supplied, not verified.',
            'Stops, hours-of-service, routing and market conditions are not modeled.',
            'ACCEPT means the supplied economic and schedule checks pass, never a booking.'],
        notice='DRAFT — NOT SENT. Internal evaluation only; confirm logistics before acting.')
