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

from pydantic import Field as ModelField

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


class OpeningPricing(Frozen):
    target_all_mile_rpm: Decimal | None = None
    operating_cpm: Decimal | None = None
    expense_claim: str | None = None
    minimum_job_charge: Decimal | None = None
    reposition_miles: Decimal | None = None
    pricing_source: str = 'carrier supplied'


class OpeningTrip(Frozen):
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
    """Owner counteroffer wins over posted payout; both require confirmation."""
    if snapshot.counter_offer is not None:
        return snapshot.counter_offer, 'owner counteroffer'
    if snapshot.draft.facts.payout is not None:
        return snapshot.draft.facts.payout, 'posted offer'
    return None, 'unknown'


_MILE_CANDIDATE = re.compile(r'(\d[\d,]*\.?\d*)\s*(?:mi|mile|miles)\b', re.IGNORECASE)


def propose_mileage(snapshot: OpeningSnapshot) -> list[str]:
    """Display-only estimate candidates from uncertainty notes. Never stored."""
    if snapshot.draft.facts.loaded_miles is not None:
        return []
    candidates = []
    for issue in snapshot.draft.issues:
        if 'est' not in issue.lower():
            continue
        for match in _MILE_CANDIDATE.finditer(issue):
            candidates.append(match.group(1).replace(',', '') + ' mi')
            if len(candidates) >= 3:
                return candidates
    return candidates


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
        return f'{value} [{snapshot.sources.get(name, "carrier")}]'
    status = 'CONFIRMED' if snapshot.confirmed else 'UNCONFIRMED'
    lines = [f'OPENING DRAFT revision {snapshot.revision} — {status}',
        'Screenshot-derived facts (verify every value):',
        f'payout: {tagged("payout", facts.payout)}',
        f'loaded miles: {tagged("loaded_miles", facts.loaded_miles)}',
        f'deadhead miles: {tagged("deadhead_miles", facts.deadhead_miles)}',
        f'weight lbs: {tagged("weight_lbs", facts.weight_lbs)}',
        'Session profile pricing (confirmed before upload unless edited):',
        f'target all-mile RPM: {tagged("target_all_mile_rpm", pricing.target_all_mile_rpm)}',
        f'operating CPM: {tagged("operating_cpm", pricing.operating_cpm)}',
        f'expense claim: {display_expense_claim(pricing.expense_claim)}',
        f'minimum job charge: {tagged("minimum_job_charge", pricing.minimum_job_charge)}',
        f'equipment: {shown(profile.equipment) if profile else "unknown"} [profile]',
        f'operating context: {shown(profile.operating_context) if profile else "unknown"} [profile]',
        'Trip context for this revision:',
        f'reposition miles: {tagged("reposition_miles", pricing.reposition_miles)}',
        f'expected duration: {tagged("duration_note", trip.duration_note)}',
        f'availability: {tagged("availability", trip.availability if trip.availability != "unknown" else None)}',
        f'handling notes: {tagged("handling_note", trip.handling_note)}']
    compensation, source = effective_compensation(snapshot)
    lines.append(f'evaluated compensation: {shown(compensation)} [{source}]')
    if snapshot.counter_note:
        lines.append(f'counteroffer note (unconfirmed): {snapshot.counter_note}')
    for issue in snapshot.draft.issues:
        lines.append('note: ' + issue)
    for candidate in propose_mileage(snapshot):
        lines.append('Possible pickup-to-delivery interpretation (UNCONFIRMED, from note): '
                     + candidate + ' — confirm explicitly or correct.')
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
                                            not isinstance(k, str) or v not in (
                                                'screenshot', 'profile', 'carrier')
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
