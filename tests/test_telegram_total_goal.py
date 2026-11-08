"""Offline owner-chat total-dollar goal regression. No live transport or model."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from test_h15_journey import store, journey
from axle_hackathon.opening_telegram import create_opening_app, negotiation_guidance
from axle_hackathon.opening_workflow import OpeningPricing, pricing_blockers
from test_h13_telegram import SECRET


def evaluate(store):
    current = store._opening.get(1, 1)
    store._opening.confirm(1, 1, current.revision)
    return store._opening.evaluate(1, 1, current.revision)


def test_total_goal_reference_and_mileage_correction(store):
    chat = journey(store, trip='reposition 20; availability feasible')
    review = chat.handle(1, 1, 'I want $480 total')
    assert '$2.00/mi' in review
    snapshot = store._opening.get(1, 1)
    assert snapshot.pricing.target_all_mile_rpm is None
    assert snapshot.pricing.target_total_payout == Decimal('480')
    assert snapshot.sources['target_total_payout'] == 'carrier'
    assert 'target_all_mile_rpm' not in snapshot.sources
    assert not pricing_blockers(snapshot)
    result = evaluate(store)
    assert (result['decision'], result['total_miles'], result['target_revenue'],
            result['revenue_gap_to_target'], result['estimated_operating_cost'],
            result['estimated_operating_surplus']) == (
                'NEGOTIATE', '240', '480.00', '60.00', '300.00', '120.00')
    assert 'DRAFT — NOT SENT' in negotiation_guidance('offer_evaluation', result)
    review = chat.handle(1, 1, 'reposition 60')
    assert '$1.71/mi' in review
    revised = store._opening.get(1, 1)
    assert not revised.confirmed
    assert store._opening.last_result(1, 1) is None
    with pytest.raises(ValueError, match='Confirm'):
        store._opening.evaluate(1, 1, revised.revision)
    assert evaluate(store)['target_revenue'] == '480.00'


def test_total_dollars_never_round_trip_through_display_rate(store):
    chat = journey(store, trip='reposition 61; availability feasible')
    chat.handle(1, 1, 'payout goal 480.01')
    assert evaluate(store)['target_revenue'] == '480.01'
    chat.handle(1, 1, 'target 2')
    assert store._opening.get(1, 1).pricing.target_total_payout is None
    assert evaluate(store)['target_revenue'] == '562.00'


@pytest.mark.parametrize('text', ['I want to clear $300', 'profit 300',
                                  'I want $800 per day', 'weekly 2000'])
def test_ambiguous_goal_clarifies_without_changing_revision(store, text):
    chat = journey(store)
    before = store._opening.get(1, 1)
    answer = chat.handle(1, 1, text)
    assert 'gross payout goal' in answer
    assert store._opening.get(1, 1) == before


@pytest.mark.parametrize('value', ['0', '-1', 'NaN', 'Infinity', '1000001'])
def test_invalid_goal_does_not_change_snapshot(store, value):
    chat = journey(store)
    before = store._opening.get(1, 1)
    with pytest.raises(ValueError):
        chat.handle(1, 1, 'payout goal ' + value)
    assert store._opening.get(1, 1) == before


def test_unknown_miles_stay_pending_and_dual_goals_rejected(store):
    chat = journey(store)
    answer = chat.handle(1, 1, 'payout goal 480')
    assert 'pending complete mileage' in answer
    assert 'reposition_miles' in pricing_blockers(store._opening.get(1, 1))
    before = store._opening.get(1, 1)
    with pytest.raises(ValueError, match='Choose'):
        chat.handle(1, 1, 'payout goal 500; target 2')
    assert store._opening.get(1, 1) == before
    with pytest.raises(ValueError, match='Choose'):
        OpeningPricing(target_total_payout=480, target_all_mile_rpm=2)


def test_total_goal_webhook_replay_has_one_revision_and_reply(store):
    chat = journey(store, trip='reposition 20; availability feasible')
    before = store._opening.get(1, 1).revision
    sent = []
    app = create_opening_app(store, webhook_secret=SECRET, allowed_host='testserver',
        conversation=chat, send=lambda c, t: sent.append(t) or True)
    payload = dict(update_id=100, message=dict(message_id=100,
        **{'from': dict(id=1, is_bot=False)}, chat=dict(id=1, type='private'),
        text='I want $480 total'))
    with TestClient(app) as client:
        first = client.post('/telegram/webhook', json=payload,
                            headers={'X-Telegram-Bot-Api-Secret-Token': SECRET})
        replay = client.post('/telegram/webhook', json=payload,
                             headers={'X-Telegram-Bot-Api-Secret-Token': SECRET})
    assert first.json()['status'] == 'processed'
    assert replay.json()['status'] == 'duplicate'
    assert store._opening.get(1, 1).revision == before + 1
    assert len(sent) == 1


def test_opening_bid_uses_total_goal_without_fabricated_offer(store):
    chat = journey(store, trip='reposition 20; availability feasible')
    chat.handle(1, 1, 'payout goal 480; payout unknown')
    current = store._opening.get(1, 1)
    store._opening.confirm(1, 1, current.revision)
    kind, result = store._opening.decide(1, 1, current.revision)
    assert kind == 'opening_bid'
    assert result['opening_bid'] == '480.00'
    assert result['estimated_operating_cost'] == '300.00'


def test_new_screenshot_does_not_inherit_load_total_goal(store):
    import test_h15_opening_workflow as h15
    chat = journey(store, trip='reposition 20; availability feasible')
    chat.handle(1, 1, 'payout goal 480')
    h15.submit_shot(store, store._active['owner'].token, update=60, message=60)
    assert h15.worker(store, []).tick() == 'completed'
    snapshot = store._opening.get(1, 1)
    assert snapshot.pricing.target_total_payout is None
    assert 'target_total_payout' not in snapshot.sources
    assert 'target_all_mile_rpm' in pricing_blockers(snapshot)
