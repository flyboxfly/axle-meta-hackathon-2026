"""Volatile real-opportunity opening revisions. No transport or model calls.

Binding is supplied by a trusted authenticated adapter, never by model output.
Screenshot-derived facts stay separate from carrier-provided pricing/context.
Every text correction or counteroffer creates a new revision and invalidates
dependent confirmations and results. Pricing uses deterministic Decimal code.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock

from .opening_bid import OpeningBidInputs, calculate_opening_bid
from .opening_intake import ScreenshotDraft
from .pilot import Frozen


class OpeningPricing(Frozen):
    target_all_mile_rpm: Decimal | None = None
    operating_cpm: Decimal | None = None
    expense_claim: str | None = None
    minimum_job_charge: Decimal | None = None
    reposition_miles: Decimal | None = None
    pricing_source: str = 'carrier supplied'


@dataclass(frozen=True)
class OpeningSnapshot:
    revision: int
    draft: ScreenshotDraft
    pricing: OpeningPricing
    counter_note: str | None = None
    confirmed: bool = False
    confirmed_at: datetime | None = None


def render_review(snapshot: OpeningSnapshot) -> str:
    """Two-section review: screenshot facts first, carrier pricing second."""
    facts = snapshot.draft.facts
    def shown(value):
        return str(value) if value is not None else 'unknown'
    lines = [f'OPENING DRAFT revision {snapshot.revision} — UNCONFIRMED',
        'Screenshot-derived facts (verify every value):',
        f'payout: {shown(facts.payout)}',
        f'loaded miles: {shown(facts.loaded_miles)}',
        f'deadhead miles: {shown(facts.deadhead_miles)}',
        f'weight lbs: {shown(facts.weight_lbs)}',
        'Carrier-provided pricing/context (never from the screenshot):',
        f'target all-mile RPM: {shown(snapshot.pricing.target_all_mile_rpm)}',
        f'operating CPM: {shown(snapshot.pricing.operating_cpm)}',
        f'expense claim: {snapshot.pricing.expense_claim or "unknown"}',
        f'minimum job charge: {shown(snapshot.pricing.minimum_job_charge)}',
        f'reposition miles: {shown(snapshot.pricing.reposition_miles)}']
    if snapshot.counter_note:
        lines.append(f'counteroffer note (unconfirmed): {snapshot.counter_note}')
    for issue in snapshot.draft.issues:
        lines.append('note: ' + issue)
    lines.append('Use /confirm to confirm this exact revision, or correct a field.')
    return '\n'.join(lines)


class OpeningSessions:
    """Process-local opening revisions. The adapter authenticates before calling."""
    def __init__(self, bindings: dict[tuple[int, int], str]):
        self._bindings = dict(bindings)
        self._sessions: dict[str, OpeningSnapshot] = {}
        self._results: dict[str, dict] = {}
        self._lock = RLock()

    def _carrier(self, user: int, chat: int) -> str:
        try:
            return self._bindings[(user, chat)]
        except KeyError:
            raise PermissionError('Unapproved private chat') from None

    def put(self, user: int, chat: int, draft: ScreenshotDraft, pricing: OpeningPricing,
            *, expected_revision: int, counter_note: str | None = None) -> OpeningSnapshot:
        with self._lock:
            carrier = self._carrier(user, chat)
            if counter_note is not None and (not counter_note or len(counter_note) > 200):
                raise ValueError('Bounded counteroffer note required')
            previous = self._sessions.get(carrier)
            if expected_revision != (previous.revision if previous else 0):
                raise ValueError('Stale revision')
            snapshot = OpeningSnapshot(expected_revision + 1, draft, pricing,
                                       counter_note=counter_note)
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
            self._results.pop(carrier, None)

    def confirm(self, user: int, chat: int, revision: int) -> OpeningSnapshot:
        with self._lock:
            carrier = self._carrier(user, chat)
            current = self._sessions[carrier]
            if current.revision != revision:
                raise ValueError('Stale confirmation')
            snapshot = OpeningSnapshot(current.revision, current.draft, current.pricing,
                counter_note=current.counter_note, confirmed=True,
                confirmed_at=datetime.now(timezone.utc))
            self._sessions[carrier] = snapshot
            return snapshot

    def price(self, user: int, chat: int, revision: int) -> dict:
        """Deterministic opening calculation for one confirmed revision."""
        with self._lock:
            carrier = self._carrier(user, chat)
            snapshot = self._sessions[carrier]
            if snapshot.revision != revision:
                raise ValueError('Stale evaluation')
            if not snapshot.confirmed:
                raise ValueError('Confirm the current snapshot first')
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
            self._results[carrier] = result
            return dict(result)
