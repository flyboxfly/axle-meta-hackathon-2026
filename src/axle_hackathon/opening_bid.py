"""Offline opening-position arithmetic, without an invented counterparty payout.

Inputs must come from a carrier-confirmed revision in the future runtime adapter.
This module grants no confirmation authority and sends nothing. CPM is a supplied
all-operating-expense estimate; itemized/excluded costs need normalization first.
"""
from decimal import Decimal
from typing import Literal

from pydantic import Field

from .pilot import Frozen, money


class OpeningBidInputs(Frozen):
    revision: int = Field(strict=True, ge=1)
    loaded_miles: Decimal = Field(gt=0, le=100000)
    deadhead_miles: Decimal | None = Field(default=None, ge=0, le=100000)
    reposition_miles: Decimal | None = Field(default=None, ge=0, le=100000)
    operating_cpm: Decimal | None = Field(default=None, ge=0, le=1000)
    expense_basis: Literal['all_operating_expenses']
    target_all_mile_rpm: Decimal | None = Field(default=None, gt=0, le=1000)
    target_total_payout: Decimal | None = Field(default=None, gt=0, le=1000000, multiple_of=Decimal("0.01"))
    # None is unknown; explicit zero means the carrier has no minimum charge.
    minimum_job_charge: Decimal | None = Field(default=None, ge=0, le=1000000)
    pricing_source: str = Field(min_length=1, max_length=200)


def calculate_opening_bid(inputs: OpeningBidInputs) -> dict:
    """Preliminary internal position; no acceptance, dispatch or reservation point.

Missing cargo/time/schedule can coexist with a preliminary price. Unknown
pricing/mileage stays unknown. Explicit reposition zero must be owner-supplied.
    """
    if inputs.target_total_payout is not None and inputs.target_all_mile_rpm is not None:
        raise ValueError('Choose a total payout goal or a per-mile target')
    missing = [name for name in ('deadhead_miles', 'reposition_miles',
        'operating_cpm', 'target_all_mile_rpm', 'minimum_job_charge')
        if getattr(inputs, name) is None
        and not (name == 'target_all_mile_rpm' and inputs.target_total_payout is not None)]
    miles = (None if inputs.deadhead_miles is None or inputs.reposition_miles is None
        else inputs.loaded_miles + inputs.deadhead_miles + inputs.reposition_miles)
    cost = (miles * inputs.operating_cpm
        if miles is not None and inputs.operating_cpm is not None else None)
    revenue = (miles * inputs.target_all_mile_rpm
        if miles is not None and inputs.target_all_mile_rpm is not None else None)
    if inputs.target_total_payout is not None:
        revenue = inputs.target_total_payout
    opening = None
    issue = None
    if not missing:
        proposed = max(revenue, inputs.minimum_job_charge)
        # Money sent to a counterparty has cents; compare at that precision.
        if Decimal(money(proposed)) <= Decimal(money(cost)):
            issue = 'Pricing rules do not leave a positive estimated operating surplus.'
        else:
            opening = proposed
    return dict(revision=inputs.revision, calculator='opening-bid-v1',
        status='PRELIMINARY_DRAFT' if opening is not None else 'PRICING_REVIEW_REQUIRED',
        total_miles=str(miles) if miles is not None else None,
        estimated_operating_cost=money(cost) if cost is not None else None,
        target_revenue=money(revenue) if revenue is not None else None,
        opening_bid=money(opening) if opening is not None else None,
        estimated_operating_surplus=(money(Decimal(money(opening))-Decimal(money(cost)))
            if opening is not None else None),
        missing=missing, pricing_issue=issue,
        notice='DRAFT — NOT SENT. Preliminary pricing; clarify cargo, handling, time '
            'and schedule during negotiation. Revised inputs require fresh review. '
            'No acceptance, booking or confirmed negotiation floor.')
