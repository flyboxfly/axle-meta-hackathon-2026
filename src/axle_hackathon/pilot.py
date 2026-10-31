"""Pure pilot core. No transport, persistence, model calls or synthetic defaults.

Binding is supplied by a trusted authenticated adapter, never by model output.
This in-memory store is not a hosted multi-process storage implementation.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from threading import RLock
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Frozen(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class PeriodAllocation(Frozen):
    """Carrier-supplied utilization for the SAME period as the cost amount."""
    cost_period: Literal['week', 'month', 'year']
    utilization_period: Literal['week', 'month', 'year']
    operating_miles: Decimal | None = Field(default=None, gt=0, le=1000000)
    source: str = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def matching_periods(self):
        if self.cost_period != self.utilization_period:
            raise ValueError('Cost and utilization periods must match; no implicit conversion')
        return self


class FuelEstimate(Frozen):
    price_per_us_gallon: Decimal | None = Field(default=None, ge=0, le=100)
    miles_per_us_gallon: Decimal | None = Field(default=None, gt=0, le=1000)


class SoftwareRecord(Frozen):
    name: str = Field(min_length=1, max_length=100)
    status: Literal['subscribed', 'planned', 'interested']
    source: str = Field(min_length=1, max_length=200)


class ProfileMetadata(Frozen):
    unit_id: str | None = Field(default=None, min_length=1, max_length=80)
    carrier_role: Literal['owner_operator', 'fleet_owner', 'dispatcher', 'driver'] | None = None
    effective_at: AwareDatetime
    recorded_at: AwareDatetime


class CostItem(Frozen):
    name: Literal['fuel', 'driver', 'insurance', 'truck_base', 'rental_mileage',
                  'maintenance', 'tolls', 'miscellaneous', 'contingency']
    amount: Decimal | None = Field(default=None, ge=0, le=1000000)
    basis: Literal['per_mile', 'per_trip', 'per_hour', 'per_period', 'fuel_mpg']
    source: str = Field(min_length=1, max_length=200)
    allocation: PeriodAllocation | None = None
    fuel: FuelEstimate | None = None
    effective_at: AwareDatetime | None = None

    @model_validator(mode='after')
    def method(self):
        if (self.basis == 'per_period') != (self.allocation is not None):
            raise ValueError('Period costs require an explicit allocation only on per_period items')
        if self.basis == 'fuel_mpg':
            if self.name != 'fuel' or self.fuel is None or self.amount is not None:
                raise ValueError('Fuel MPG method requires fuel inputs and no separate amount')
        elif self.fuel is not None:
            raise ValueError('Fuel inputs require fuel_mpg basis')
        return self

    def missing_inputs(self) -> tuple[str, ...]:
        if self.basis == 'fuel_mpg':
            return tuple('fuel:' + key for key in ('price_per_us_gallon', 'miles_per_us_gallon')
                         if getattr(self.fuel, key) is None)
        missing = ['cost:' + self.name] if self.amount is None else []
        if self.allocation is not None and self.allocation.operating_miles is None:
            missing.append('utilization:' + self.name)
        return tuple(missing)

    def trip_amount(self, miles: Decimal, hours: Decimal | None) -> Decimal:
        if self.missing_inputs() or (self.basis == 'per_hour' and hours is None):
            raise ValueError('Unresolved cost inputs')
        if self.basis == 'fuel_mpg':
            return miles / self.fuel.miles_per_us_gallon * self.fuel.price_per_us_gallon
        if self.basis == 'per_period':
            return self.amount * miles / self.allocation.operating_miles
        if self.basis == 'per_hour':
            return self.amount * hours
        return self.amount * miles if self.basis == 'per_mile' else self.amount


class Profile(Frozen):
    equipment: str = Field(min_length=1, max_length=80)
    arrangement: Literal['owned', 'financed', 'rented']
    mode: Literal['itemized', 'all_in_cpm']
    items: tuple[CostItem, ...] = ()
    cpm: Decimal | None = Field(default=None, ge=0, le=1000)
    # CPM must explicitly account for every category, including zero/not applicable.
    cpm_includes: tuple[str, ...] = ()
    maintenance_covered_by_rental: bool | None = None
    target_all_mile_rpm: Decimal | None = Field(default=None, gt=0, le=1000)
    priorities: tuple[str, ...] = ()
    software: tuple[SoftwareRecord, ...] = ()
    metadata: ProfileMetadata | None = None
    source: str = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def accounting(self):
        names = [i.name for i in self.items]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate cost category')
        categories = set(CostItem.model_fields['name'].annotation.__args__)
        included = set(self.cpm_includes)
        if len(included) != len(self.cpm_includes) or not included <= categories:
            raise ValueError('Invalid CPM inclusion map')
        if self.mode == 'itemized' and (self.cpm is not None or included):
            raise ValueError('Do not combine cost modes')
        if self.mode == 'all_in_cpm':
            if self.cpm is None or included | set(names) != categories or included & set(names):
                raise ValueError('CPM requires complete nonoverlapping inclusions/exclusions')
        if self.arrangement == 'rented' and self.maintenance_covered_by_rental is True:
            maintenance = next((i for i in self.items if i.name == 'maintenance'), None)
            if maintenance and maintenance.amount != Decimal(0):
                raise ValueError('Covered maintenance cannot be charged again')
        return self


class Opportunity(Frozen):
    payout: Decimal = Field(ge=0, le=1000000)
    loaded_miles: Decimal = Field(gt=0, le=100000)
    deadhead_miles: Decimal | None = Field(default=None, ge=0, le=100000)
    reposition_miles: Decimal | None = Field(default=None, ge=0, le=100000)
    # Total compensated/planned trip time, including supplied dwell/handling.
    trip_hours: Decimal | None = Field(default=None, ge=0, le=10000)
    schedule: Literal['feasible', 'conflict', 'unknown'] = 'unknown'
    scope: str = Field(min_length=1, max_length=2000)
    origin: Literal['real_offer', 'synthetic']
    operation: Literal['current_confirmed', 'hypothetical']
    source: str = Field(min_length=1, max_length=200)


@dataclass(frozen=True)
class Snapshot:
    revision: int
    profile: Profile
    opportunity: Opportunity
    confirmed: bool = False
    confirmed_at: datetime | None = None


def money(value):
    return str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def calculate(snapshot: Snapshot) -> dict:
    """Return canonical planning economics only for an explicitly confirmed snapshot."""
    if not snapshot.confirmed:
        raise ValueError('Confirm the current snapshot first')
    p, o = snapshot.profile, snapshot.opportunity
    missing = []
    for name in ('deadhead_miles', 'reposition_miles'):
        if getattr(o, name) is None:
            missing.append(name)
    miles = None if missing else o.loaded_miles + o.deadhead_miles + o.reposition_miles
    required = {'fuel', 'driver', 'insurance', 'truck_base', 'maintenance', 'tolls', 'miscellaneous', 'contingency'}
    if p.arrangement == 'rented':
        required.add('rental_mileage')
        if p.maintenance_covered_by_rental is None:
            missing.append('rental_maintenance_coverage')
    names = {i.name for i in p.items} | set(p.cpm_includes)
    missing.extend('cost:' + name for name in sorted(required - names))
    missing.extend(key for i in p.items for key in i.missing_inputs())
    if o.trip_hours is None and any(i.basis == 'per_hour' for i in p.items):
        missing.append('trip_hours')
    cost_missing = any(m.startswith(('cost:', 'rental_', 'fuel:', 'utilization:', 'trip_hours'))
                       for m in missing)
    cost = None
    reserve = None
    if miles is not None and not cost_missing:
        cost = (p.cpm * miles if p.mode == 'all_in_cpm' else Decimal(0))
        for i in p.items:
            cost += i.trip_amount(miles, o.trip_hours)
        # A CPM containing contingency does not identify the reserve separately.
        reserve = None if 'contingency' in p.cpm_includes else sum(
            i.trip_amount(miles, o.trip_hours)
            for i in p.items if i.name == 'contingency')
    if p.target_all_mile_rpm is None:
        missing.append('target_all_mile_rpm')
    if o.schedule == 'unknown':
        missing.append('schedule')
    target = miles * p.target_all_mile_rpm if miles is not None and p.target_all_mile_rpm is not None else None
    decision = 'NEED_MORE_INFORMATION'
    if o.schedule == 'conflict':
        decision = 'DECLINE'
    elif not missing:
        decision = 'NEGOTIATE' if o.payout < target or o.payout <= cost else 'ACCEPT'
    return dict(revision=snapshot.revision, profile_source=p.source,
                opportunity_origin=o.origin, operating_scenario=o.operation,
                calculator='pilot-v2', decision=decision, missing=missing,
                confirmed_at=snapshot.confirmed_at.isoformat() if snapshot.confirmed_at else None,
                declared_cpm_cost=money(p.cpm * miles)
                    if p.mode == 'all_in_cpm' and miles is not None else None,
                cost_breakdown=tuple(dict(name=i.name, basis=i.basis, source=i.source,
                    amount=money(i.trip_amount(miles, o.trip_hours))
                    if miles is not None and not i.missing_inputs()
                    and (i.basis != 'per_hour' or o.trip_hours is not None) else None)
                    for i in p.items),
                total_miles=str(miles) if miles is not None else None,
                loaded_rpm=money(o.payout/o.loaded_miles),
                all_mile_rpm=money(o.payout/miles) if miles is not None else None,
                planning_cost_including_reserves=money(cost) if cost is not None else None,
                contingency=money(reserve) if reserve is not None else None,
                planning_surplus=money(o.payout-cost) if cost is not None else None,
                target_revenue=money(target) if target is not None else None,
                gap=money(max(Decimal(0), target-o.payout)) if target is not None else None,
                limitation='Planning estimates; no booking, accounting profit or regulatory clearance.')


class PilotSessions:
    """Volatile, process-local sessions. No reusable profile persistence or authentication.

    The future Telegram adapter must authenticate numeric IDs before calling these methods.
    Every binding is checked; opportunity revisions cannot overwrite another carrier's state.
    """
    def __init__(self, bindings: dict[tuple[int, int], str]):
        self._bindings = dict(bindings)
        self._sessions = {}
        self._results = {}
        self._lock = RLock()

    def _carrier(self, user: int, chat: int) -> str:
        try:
            return self._bindings[(user, chat)]
        except KeyError:
            raise PermissionError('Unapproved private chat') from None

    def put(self, user: int, chat: int, profile: Profile, opportunity: Opportunity,
            *, expected_revision: int) -> Snapshot:
        with self._lock:
            carrier = self._carrier(user, chat)
            previous = self._sessions.get(carrier)
            if expected_revision != (previous.revision if previous else 0):
                raise ValueError('Stale revision')
            snapshot = Snapshot(expected_revision + 1, profile, opportunity)
            self._sessions[carrier] = snapshot
            self._results.pop(carrier, None)
            return snapshot

    def get(self, user: int, chat: int) -> Snapshot:
        with self._lock:
            return self._sessions[self._carrier(user, chat)]

    def clear(self, user: int, chat: int):
        """Trusted facade expiry/withdrawal; its consent token prevents revision reuse."""
        with self._lock:
            carrier = self._carrier(user, chat)
            self._sessions.pop(carrier, None)
            self._results.pop(carrier, None)

    def confirm(self, user: int, chat: int, revision: int) -> Snapshot:
        with self._lock:
            carrier = self._carrier(user, chat)
            s = self._sessions[carrier]
            if s.revision != revision:
                raise ValueError('Stale confirmation')
            s = Snapshot(s.revision, s.profile, s.opportunity, True, datetime.now(timezone.utc))
            self._sessions[carrier] = s
            return s

    def evaluate(self, user: int, chat: int, revision: int) -> dict:
        with self._lock:
            carrier = self._carrier(user, chat)
            s = self._sessions[carrier]
            if s.revision != revision:
                raise ValueError('Stale evaluation')
            result = calculate(s)
            self._results[carrier] = result
            return dict(result)
