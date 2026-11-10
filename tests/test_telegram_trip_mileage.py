"""Offline Telegram webhook acceptance for trip endpoints and mileage."""
import json
import re

from fastapi.testclient import TestClient
import pytest

from axle_hackathon.opening_telegram import OpeningConversation, create_opening_app
from axle_hackathon.pilot_runtime import OpeningWorker
from test_h13_telegram import SECRET
from test_h15_opening_workflow import (delegator, draft_text, extraction_response,
                                      selection_response, store)
from test_h15_journey import journey


def test_two_opportunities_with_fresh_trip_and_exact_revision(store):
    conversation = OpeningConversation(store)
    sent, calls = [], []
    offers = iter(('420', '460'))
    inner = delegator(store, calls)

    def extract(**_):
        pay = next(offers)
        return extraction_response(draft_text(
            payout=(pay, f'Total payout ${pay}'), loaded_miles=('180', 'Loaded 180 mi')))

    def select(**payload):
        inputs = json.loads(payload['input'])
        assert set(inputs['trip']) == {'duration_note', 'availability', 'handling_note'}
        calls.append(inputs['revision'])
        return selection_response(inputs['revision'])

    inner._image.responses.create = extract
    inner._text.responses.create = select

    def send(chat, text):
        assert chat == 1
        sent.append(text)
        return True

    app = create_opening_app(store, webhook_secret=SECRET, allowed_host='testserver',
                             conversation=conversation, send=send)
    with TestClient(app) as client:
        worker = OpeningWorker(store, inner, send, global_limit=4, carrier_limit=4)

        def post(update, **fields):
            return client.post('/telegram/webhook',
                headers={'X-Telegram-Bot-Api-Secret-Token': SECRET},
                json={'update_id': update, 'message': {
                    'message_id': update, 'from': {'id': 1, 'is_bot': False},
                    'chat': {'id': 1, 'type': 'private'}, **fields}}).json()['status']

        def nonce():
            return re.search(r'Step: (\S+)', sent[-1])[1]

        def photo(update):
            assert post(update, document={'file_id': f'file-{update}',
                'file_unique_id': f'fictional-{update}', 'file_size': 100, 'mime_type': 'image/png',
                'file_name': 'fictional.png'}) == 'queued'
            assert worker.tick() == 'completed'

        assert post(1, text='/start') == 'processed'
        assert post(2, text=f'/reply {nonce()} remember') == 'processed'
        assert post(3, text='cpm 1.25; target 2.00; minimum none; unit BOX-01') == 'processed'
        assert post(4, text='save profile') == 'processed'
        photo(5)
        assert post(6, text='truck position West Yard; deadhead 0; next destination East Yard; '
                            'reposition 20; availability blocked; payout goal 480; counter 650') == 'processed'
        assert 'miles to pickup: 0 [carrier]' in sent[-1]
        assert post(7, text=f'/confirm {nonce()}') == 'processed'

        assert post(8, text='/price') == 'queued'
        assert worker.tick() == 'completed'
        assert 'DECLINE' in sent[-1]

        photo(9)
        second = store._opening.get(1, 1)
        assert 'truck: BOX-01 [profile]' in sent[-1]
        assert second.trip.truck_position is second.trip.approximate_truck_pin is None
        assert second.trip.next_destination is second.pricing.reposition_miles is None
        assert second.trip.availability == 'unknown'
        assert second.pricing.target_total_payout is second.counter_offer is None
        assert second.draft.facts.deadhead_miles is None

        pin = {'latitude': 10.123456, 'longitude': 20.654321}
        assert post(10, location={**pin, 'live_period': 60}) == 'unsupported_update'
        assert post(10, location=pin) == 'processed'
        assert post(10, location=pin) == 'duplicate'
        assert store._opening.get(1, 1).trip.approximate_truck_pin == (10.12, 20.65)
        assert '10.123456' not in sent[-1] and '20.654321' not in sent[-1]
        assert 'truck position: shared pin' in sent[-1]
        assert 'miles to pickup: unknown' in sent[-1]
        assert post(11, text='home') == 'processed'
        assert post(12, text='deadhead 30; reposition 35; availability feasible') == 'processed'
        assert 'next destination: home [carrier]' in sent[-1]
        assert 'miles to pickup: 30 [carrier]' in sent[-1]
        assert 'loaded miles: 180 [screenshot]' in sent[-1]
        assert 'miles after delivery: 35 [carrier]' in sent[-1]
        review_nonce = nonce()
        assert post(13, text=f'/confirm {review_nonce}') == 'processed'
        assert post(14, text='/price') == 'queued'
        assert worker.tick() == 'completed'
        assert 'Total miles: 245' in sent[-1]
        assert 'Estimated operating cost: $306.25' in sent[-1]
        assert 'Target revenue: $490.00' in sent[-1]
        assert 'Revenue gap to target: $30.00' in sent[-1]
        assert 'DRAFT — NOT SENT' in sent[-1]

        assert post(15, text='next destination yard') == 'processed'
        changed = store._opening.get(1, 1)
        assert not changed.confirmed and changed.pricing.reposition_miles is None
        assert changed.draft.facts == second.draft.facts.model_copy(update={'deadhead_miles': 30})
        assert post(16, text=f'/confirm {review_nonce}') == 'processed'
        assert not store._opening.get(1, 1).confirmed
        assert post(17, text='/price') == 'invalid_update'
        assert post(18, text=f'/confirm {nonce()}') == 'processed'
        assert post(19, text='/price') == 'invalid_update'
        assert len(calls) == 2
        assert post(20, text='reposition 0') == 'processed'
        assert 'miles after delivery: 0 [carrier]' in sent[-1]
        assert not store._opening.get(1, 1).confirmed

        assert post(21, text=f'/confirm {nonce()}') == 'processed'
        assert post(22, location={'latitude': 11.234567, 'longitude': 21.234567}) == 'processed'
        moved = store._opening.get(1, 1)
        assert not moved.confirmed and moved.draft.facts.deadhead_miles is None
        assert moved.draft.facts.loaded_miles == 180 and moved.pricing.reposition_miles == 0

    records = '\n'.join(store._db.iterdump())
    for trip_data in ('West Yard', 'East Yard', '10.123456', '10.12', '20.65'):
        assert trip_data not in records


@pytest.mark.parametrize('correction, expected', [
    ('truck position Clear Lake', (None, 180, 20)),
    ('pickup North Dock', (None, None, 20)),
    ('delivery South Dock', (40, None, None)),
    ('pickup North Dock; deadhead 0; loaded 175', (0, 175, 20)),
])
def test_endpoint_edits_clear_only_dependent_legs(store, correction, expected):
    conversation = journey(store, 'truck position Yard A; pickup Dock A; delivery Dock B; '
                                  'loaded 180; deadhead 40; next destination home; reposition 20')
    nonce = store._conversation_states['owner']['nonce']
    conversation.handle(1, 1, f'/confirm {nonce}')
    conversation.handle(1, 1, correction)
    snapshot = store._opening.get(1, 1)
    assert not snapshot.confirmed
    assert (snapshot.draft.facts.deadhead_miles, snapshot.draft.facts.loaded_miles,
            snapshot.pricing.reposition_miles) == expected
