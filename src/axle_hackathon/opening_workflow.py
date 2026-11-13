"""Volatile real-opportunity opening revisions. No transport or model calls.

Binding is supplied by a trusted authenticated adapter, never by model output.
Screenshot-derived facts, the confirmed session profile, carrier trip context
and later carrier corrections stay labeled by source. Every correction or
counteroffer creates a new revision and invalidates dependent confirmations
and results. Pricing uses deterministic Decimal code.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock
import re
from typing import Literal

from pydantic import Field as ModelField, model_validator

from .opening_bid import OpeningBidInputs, calculate_opening_bid
from .opening_evaluate import OfferInputs, evaluate_offer
from .opening_intake import ScreenshotDraft
from .pilot import Frozen


class OpeningProfile(Frozen):
    """Session template confirmed before screenshot upload. No defaults."""
    operating_cpm: Decimal | None = None
    expense_claim: str | None = None
    target_all_mile_rpm: Decimal | None = None
    minimum_job_charge: Decimal | None = None
    equipment: str | None = ModelField(default=None, max_length=200)
    operating_context: str | None = ModelField(default=None, max_length=500)
    # Carrier assertions only. Authenticated tenant is still the adapter binding.
    usdot: str | None = ModelField(default=None, pattern=r'^[0-9]{1,8}$')
    mc: str | None = ModelField(default=None, pattern=r'^[0-9]{1,8}$')
    unit_number: str | None = ModelField(default=None, max_length=80)
    truck_nickname: str | None = ModelField(default=None, max_length=80)
    capabilities: str | None = ModelField(default=None, max_length=200)
    arrangement: Literal['owned', 'financed', 'rented'] | None = None
    home_base: str | None = ModelField(default=None, max_length=200)


class OpeningPricing(Frozen):
    target_total_payout: Decimal | None = ModelField(default=None, gt=0, le=1000000, multiple_of=Decimal("0.01"))
    target_all_mile_rpm: Decimal | None = None
    operating_cpm: Decimal | None = None
    expense_claim: str | None = None
    minimum_job_charge: Decimal | None = None
    reposition_miles: Decimal | None = None
    pricing_source: str = 'carrier supplied'

    @model_validator(mode='after')
    def one_goal_basis(self):
        if self.target_total_payout is not None and self.target_all_mile_rpm is not None:
            raise ValueError('Choose a total payout goal or a per-mile target')
        return self


class OpeningTrip(Frozen):
    truck_position: str | None = ModelField(default=None, max_length=64)
    # Rounded in the Telegram adapter; never shown or sent for pricing.
    approximate_truck_pin: tuple[float, float] | None = None
    pickup: str | None = ModelField(default=None, max_length=64)
    delivery: str | None = ModelField(default=None, max_length=64)
    next_destination: str | None = ModelField(default=None, max_length=200)
    duration_note: str | None = ModelField(default=None, max_length=200)
    availability: Literal['unknown', 'feasible', 'blocked'] = 'unknown'
    handling_note: str | None = ModelField(default=None, max_length=500)


@dataclass(frozen=True)
class OpeningSnapshot:
    revision: int
    draft: ScreenshotDraft
    pricing: OpeningPricing
    trip: OpeningTrip = field(default_factory=OpeningTrip)
    counter_offer: Decimal | None = None
    counter_note: str | None = None
    sources: dict = field(default_factory=dict)
    confirmed: bool = False
    confirmed_at: datetime | None = None


def effective_compensation(snapshot: OpeningSnapshot) -> tuple[Decimal | None, str]:
    """A revised amount takes precedence over the original posted payout."""
    if snapshot.counter_offer is not None:
        source = ('revised broker offer' if snapshot.sources.get('counter_offer') == 'broker'
                  else 'owner counteroffer')
        return snapshot.counter_offer, source
    if snapshot.draft.facts.payout is not None:
        return snapshot.draft.facts.payout, 'posted offer'
    return None, 'unknown'


_MILE_CANDIDATE = re.compile(r'(\d[\d,]*\.?\d*)\s*(?:mi|mile|miles)\b', re.IGNORECASE)


def mileage_candidates(snapshot: OpeningSnapshot) -> list[dict]:
    """Structured estimated-mileage candidates from uncertainty notes.

    Display/input data only: a candidate is never stored as loaded miles.
    The carrier adopts one explicitly (a correction creates a new revision
    with carrier source and needs fresh confirmation), or corrects it.
    """
    if (snapshot.draft.facts.loaded_miles is not None
            or snapshot.draft.evidence.get('loaded_miles') == 'carrier correction'):
        return []
    candidates, seen = [], set()
    for issue in snapshot.draft.issues:
        if 'est' not in issue.lower():
            continue
        for match in _MILE_CANDIDATE.finditer(issue):
            try:
                value = Decimal(match.group(1).replace(',', ''))
            except Exception:
                continue
            if not value.is_finite() or not 0 < value <= 100000:
                continue
            text = format(value.normalize(), 'f') if value == value.to_integral() else str(value)
            if text in seen:
                continue
            seen.add(text)
            candidates.append(dict(field='loaded_miles', value=text, unit='mi',
                                   source_text=issue[:240]))
            if len(candidates) >= 3:
                return candidates
    return candidates


def propose_mileage(snapshot: OpeningSnapshot) -> list[str]:
    """Display labels for mileage_candidates. Never stored as miles."""
    return [candidate['value'] + ' mi' for candidate in mileage_candidates(snapshot)]


def pricing_blockers(snapshot: OpeningSnapshot) -> list[str]:
    """Every input a usable bid needs, checked server-side before spending.

    Loaded, pickup and after-delivery miles, all-operating-expense CPM,
    asking rate and minimum charge (explicit zero allowed where permitted)
    must all be present before any pricing queue, reservation or model
    call, on both the bot and Mini App paths. Schedule, cargo, weight and
    handling stay advisory: they never block a preliminary price.
    """
    facts, pricing = snapshot.draft.facts, snapshot.pricing
    blockers = []
    if facts.loaded_miles is None:
        blockers.append('loaded_miles')
    if facts.deadhead_miles is None:
        blockers.append('deadhead_miles')
    if pricing.reposition_miles is None:
        blockers.append('reposition_miles')
    if pricing.operating_cpm is None:
        blockers.append('operating_cpm')
    if pricing.target_all_mile_rpm is None and pricing.target_total_payout is None:
        blockers.append('target_all_mile_rpm')
    if pricing.minimum_job_charge is None:
        blockers.append('minimum_job_charge')
    if pricing.expense_claim != 'all_operating_expenses':
        blockers.append('expense_claim')
    return blockers


# Familiar carrier-facing labels for required pricing inputs; underlying
# field names, Decimal values and provenance are unchanged.
MISSING_INPUT_LABELS = {
    'loaded_miles': 'loaded miles',
    'deadhead_miles': 'miles to pickup',
    'reposition_miles': 'miles after delivery',
    'operating_cpm': 'your cost per mile',
    'target_all_mile_rpm': 'your payout goal (total dollars or per mile)',
    'minimum_job_charge': 'lowest total you will accept',
    'expense_claim': 'all-operating-expense cost basis',
}


def missing_input_labels(blockers) -> list[str]:
    return [MISSING_INPUT_LABELS.get(name, name) for name in blockers]


def display_expense_claim(value):
    """Carrier-facing expense-claim label; the stored value is unchanged."""
    if value == 'all_operating_expenses':
        return 'All operating expenses'
    return str(value) if value else 'unknown'


def render_review(snapshot: OpeningSnapshot, profile: OpeningProfile | None = None) -> str:
    """Consolidated review with accurate per-value source labels."""
    facts = snapshot.draft.facts
    pricing = snapshot.pricing
    trip = snapshot.trip
    def shown(value):
        return str(value) if value is not None else 'unknown'
    def tagged(name, value):
        if value is None:
            return 'unknown'
        source = snapshot.sources.get(name, 'carrier')
        if name in ('deadhead_miles', 'reposition_miles') and source.endswith('estimate'):
            value = f'{value:.2f}'
        return f'{value} [{source}]'
    status = 'CONFIRMED' if snapshot.confirmed else 'UNCONFIRMED'
    lines = [f'OPENING DRAFT revision {snapshot.revision} — {status}',
        'From your screenshot (check every value):',
        f'posted pay: {tagged("payout", facts.payout)}',
        f'weight lbs: {tagged("weight_lbs", facts.weight_lbs)}',
        'Your pricing inputs (rates use all trip miles below):',
        f'desired total payout: {tagged("target_total_payout", pricing.target_total_payout)}',
        f'your asking rate per mile: {tagged("target_all_mile_rpm", pricing.target_all_mile_rpm)}',
        f'your cost per mile: {tagged("operating_cpm", pricing.operating_cpm)}',
        f'cost basis: {display_expense_claim(pricing.expense_claim)}',
        f'lowest total you will accept: {tagged("minimum_job_charge", pricing.minimum_job_charge)}',
        f'equipment: {shown(profile.equipment) if profile else "unknown"} [profile]',
        f'truck: {shown(profile.unit_number or profile.truck_nickname) if profile else "unknown"} [profile]',
        f'operating context: {shown(profile.operating_context) if profile else "unknown"} [profile]',
        'This trip:',
        'truck position: ' + ('shared pin [carrier; approximate]' if trip.approximate_truck_pin
                              else tagged('truck_position', trip.truck_position)),
        f'pickup: {tagged("pickup", trip.pickup)}',
        f'delivery: {tagged("delivery", trip.delivery)}',
        f'next destination: {tagged("next_destination", trip.next_destination)}',
        'Mileage legs (no route verification):',
        f'miles to pickup: {tagged("deadhead_miles", facts.deadhead_miles)}',
        f'loaded miles: {tagged("loaded_miles", facts.loaded_miles)}',
        f'miles after delivery: {tagged("reposition_miles", pricing.reposition_miles)}',
        f'expected duration: {tagged("duration_note", trip.duration_note)}',
        f'availability: {tagged("availability", trip.availability if trip.availability != "unknown" else None)}',
        f'handling notes: {tagged("handling_note", trip.handling_note)}']
    if trip.next_destination == 'home':
        home = shown(profile.home_base if profile else None)
        lines.append(f'Saved home base for this next stop: {home}. Review before confirming.')
    if snapshot.sources.get('reposition_miles') == 'TomTom estimate' and not snapshot.confirmed:
        lines.append('Review the estimated miles after delivery before confirming, or enter reposition miles manually.')
    if snapshot.sources.get('deadhead_miles') in ('offline route estimate', 'TomTom estimate') and not snapshot.confirmed:
        lines.append('Review the estimated miles to pickup before confirming, or replace them '
                     'by replying with deadhead followed by your mileage.')
    if pricing.target_total_payout is not None:
        segments = (facts.loaded_miles, facts.deadhead_miles, pricing.reposition_miles)
        miles = sum(segments) if all(v is not None for v in segments) else None
        rate = f'${pricing.target_total_payout / miles:.2f}/mi' if miles else 'pending complete mileage'
        lines.append(f'Total payout goal equivalent: {rate} across all trip miles; total dollars stay fixed.')
    compensation, source = effective_compensation(snapshot)
    lines.append(f'evaluated compensation: {shown(compensation)} [{source}]')
    if snapshot.counter_note:
        lines.append(f'counteroffer note (unconfirmed): {snapshot.counter_note}')
    for issue in snapshot.draft.issues:
        lines.append('note: ' + issue)
    for candidate in mileage_candidates(snapshot):
        lines.append('Possible pickup-to-delivery interpretation (UNCONFIRMED, from note): '
                     + candidate['value'] + ' mi'
                     + ' (estimate) — to enter a planning value reply: loaded ' + candidate['value']
                     + ' (new revision, fresh confirmation needed), or correct it.')
    missing_legs = [label for label, value in (
        ('deadhead', facts.deadhead_miles), ('loaded', facts.loaded_miles),
        ('reposition', pricing.reposition_miles)) if value is None]
    if missing_legs:
        lines.append('Add missing mileage with these labels: ' + ', '.join(missing_legs) + '.')
    lines.append('Use /confirm to confirm this exact revision, or correct a field.')
    return '\n'.join(lines)


class OpeningSessions:
    """Process-local opening revisions. The adapter authenticates before calling."""
    def __init__(self, bindings: dict[tuple[int, int], str]):
        self._bindings = dict(bindings)
        self._sessions: dict[str, OpeningSnapshot] = {}
        self._profiles: dict[str, OpeningProfile] = {}
        self._profile_versions: dict[str, int] = {}
        self._results: dict[str, dict] = {}
        self._lock = RLock()

    def _carrier(self, user: int, chat: int) -> str:
        try:
            return self._bindings[(user, chat)]
        except KeyError:
            raise PermissionError('Unapproved private chat') from None

    def set_profile(self, user: int, chat: int, profile: OpeningProfile) -> OpeningProfile:
        with self._lock:
            carrier = self._carrier(user, chat)
            self._profiles[carrier] = profile
            self._profile_versions[carrier] = self._profile_versions.get(carrier, 0) + 1
            return profile

    def get_profile(self, user: int, chat: int) -> OpeningProfile:
        with self._lock:
            return self._profiles[self._carrier(user, chat)]

    def profile_version(self, user: int, chat: int) -> int:
        """Monotonic profile writes, 0 when never set. Never reset on clear."""
        with self._lock:
            return self._profile_versions.get(self._carrier(user, chat), 0)

    def set_profile_expected(self, user: int, chat: int, profile: OpeningProfile,
                             *, expected_version: int) -> OpeningProfile:
        """Atomic compare-and-set: rejects when another surface wrote first."""
        with self._lock:
            carrier = self._carrier(user, chat)
            if self._profile_versions.get(carrier, 0) != expected_version:
                raise ValueError('Stale profile submission')
            self._profiles[carrier] = profile
            self._profile_versions[carrier] = expected_version + 1
            return profile

    def put(self, user: int, chat: int, draft: ScreenshotDraft, pricing: OpeningPricing,
            *, expected_revision: int, trip: OpeningTrip | None = None,
            counter_offer: Decimal | None = None, counter_note: str | None = None,
            sources: dict | None = None) -> OpeningSnapshot:
        with self._lock:
            carrier = self._carrier(user, chat)
            if counter_note is not None and (not counter_note or len(counter_note) > 200):
                raise ValueError('Bounded counteroffer note required')
            if counter_offer is not None and (
                    not isinstance(counter_offer, Decimal) or counter_offer < 0
                    or counter_offer > 1000000):
                raise ValueError('Bounded numeric counteroffer required')
            if sources is not None and (not isinstance(sources, dict)
                                        or len(sources) > 24 or any(
                                            not isinstance(k, str) or (v not in (
                                                'screenshot', 'profile', 'carrier', 'offline route estimate', 'TomTom estimate')
                                            and (k, v) != ('counter_offer', 'broker'))
                                            for k, v in sources.items())):
                raise ValueError('Valid source labels required')
            previous = self._sessions.get(carrier)
            if expected_revision != (previous.revision if previous else 0):
                raise ValueError('Stale revision')
            snapshot = OpeningSnapshot(expected_revision + 1, draft, pricing,
                                       trip=trip or OpeningTrip(),
                                       counter_offer=counter_offer,
                                       counter_note=counter_note,
                                       sources=dict(sources or {}))
            self._sessions[carrier] = snapshot
            self._results.pop(carrier, None)
            return snapshot

    def get(self, user: int, chat: int) -> OpeningSnapshot:
        with self._lock:
            return self._sessions[self._carrier(user, chat)]

    def clear(self, user: int, chat: int):
        with self._lock:
            carrier = self._carrier(user, chat)
            self._sessions.pop(carrier, None)
            self._profiles.pop(carrier, None)
            self._results.pop(carrier, None)

    def confirm(self, user: int, chat: int, revision: int) -> OpeningSnapshot:
        with self._lock:
            carrier = self._carrier(user, chat)
            current = self._sessions[carrier]
            if current.revision != revision:
                raise ValueError('Stale confirmation')
            snapshot = OpeningSnapshot(current.revision, current.draft, current.pricing,
                trip=current.trip, counter_offer=current.counter_offer,
                counter_note=current.counter_note, sources=dict(current.sources),
                confirmed=True, confirmed_at=datetime.now(timezone.utc))
            self._sessions[carrier] = snapshot
            return snapshot

    def _checked(self, user: int, chat: int, revision: int) -> OpeningSnapshot:
        carrier = self._carrier(user, chat)
        snapshot = self._sessions[carrier]
        if snapshot.revision != revision:
            raise ValueError('Stale evaluation')
        if not snapshot.confirmed:
            raise ValueError('Confirm the current snapshot first')
        return snapshot

    def price(self, user: int, chat: int, revision: int) -> dict:
        """Deterministic opening calculation for one confirmed revision."""
        with self._lock:
            snapshot = self._checked(user, chat, revision)
            if snapshot.pricing.expense_claim != 'all_operating_expenses':
                raise ValueError('Explicit all-operating-expense CPM required; '
                                 'itemized costs need normalization first')
            facts = snapshot.draft.facts
            if facts.loaded_miles is None:
                raise ValueError('Confirmed loaded miles required')
            result = calculate_opening_bid(OpeningBidInputs(
                revision=snapshot.revision, loaded_miles=facts.loaded_miles,
                deadhead_miles=facts.deadhead_miles,
                reposition_miles=snapshot.pricing.reposition_miles,
                operating_cpm=snapshot.pricing.operating_cpm,
                expense_basis='all_operating_expenses',
                target_all_mile_rpm=snapshot.pricing.target_all_mile_rpm,
                target_total_payout=snapshot.pricing.target_total_payout,
                minimum_job_charge=snapshot.pricing.minimum_job_charge,
                pricing_source=snapshot.pricing.pricing_source))
            self._results[self._carrier(user, chat)] = ('opening_bid', result)
            return dict(result)

    def evaluate(self, user: int, chat: int, revision: int) -> dict:
        """Deterministic offer evaluation for one confirmed revision."""
        with self._lock:
            snapshot = self._checked(user, chat, revision)
            if snapshot.pricing.expense_claim != 'all_operating_expenses':
                raise ValueError('Explicit all-operating-expense CPM required; '
                                 'itemized costs need normalization first')
            compensation, source = effective_compensation(snapshot)
            if compensation is None:
                raise ValueError('Confirmed compensation required')
            result = evaluate_offer(OfferInputs(
                revision=snapshot.revision, compensation=compensation,
                compensation_source=source, loaded_miles=snapshot.draft.facts.loaded_miles,
                deadhead_miles=snapshot.draft.facts.deadhead_miles,
                reposition_miles=snapshot.pricing.reposition_miles,
                operating_cpm=snapshot.pricing.operating_cpm,
                target_all_mile_rpm=snapshot.pricing.target_all_mile_rpm,
                target_total_payout=snapshot.pricing.target_total_payout,
                minimum_job_charge=snapshot.pricing.minimum_job_charge,
                schedule_feasible={'feasible': True, 'blocked': False}.get(
                    snapshot.trip.availability),
                pricing_source=snapshot.pricing.pricing_source))
            self._results[self._carrier(user, chat)] = ('offer_evaluation', result)
            return dict(result)

    def last_result(self, user: int, chat: int) -> tuple[str, dict] | None:
        """Stored (kind, result) for the latest evaluation, if any. No model use."""
        with self._lock:
            stored = self._results.get(self._carrier(user, chat))
            if stored is None:
                return None
            kind, result = stored
            return kind, dict(result)

    def decide(self, user: int, chat: int, revision: int) -> tuple[str, dict]:
        """Branch deterministically: known compensation evaluates, else open."""
        with self._lock:
            snapshot = self._checked(user, chat, revision)
            compensation, _ = effective_compensation(snapshot)
            if compensation is not None:
                return 'offer_evaluation', self.evaluate(user, chat, revision)
            return 'opening_bid', self.price(user, chat, revision)
