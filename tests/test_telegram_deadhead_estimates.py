"""Offline Telegram acceptance with fictional route data."""
from contextlib import contextmanager
from decimal import Decimal
import re

from fastapi.testclient import TestClient
import pytest

from axle_hackathon.opening_telegram import OpeningConversation, create_opening_app
from axle_hackathon.pilot_runtime import OpeningWorker
from test_h13_telegram import SECRET
from test_h15_journey import journey
from test_h15_opening_workflow import delegator, store


@pytest.fixture
def telegram(store):
    @contextmanager
    def connect(conversation):
        sent = []

        def send(chat, text):
            assert chat == 1
            sent.append(text)
            return True

        app = create_opening_app(store, webhook_secret=SECRET, allowed_host='testserver',
                                 conversation=conversation, send=send)
        with TestClient(app) as client:
            yield client, sent, OpeningWorker(
                store, delegator(store, []), send, global_limit=4, carrier_limit=4)

    return connect


def post(client, update, **fields):
    response = client.post('/telegram/webhook',
        headers={'X-Telegram-Bot-Api-Secret-Token': SECRET},
        json={'update_id': update, 'message': {
            'message_id': update, 'from': {'id': 1, 'is_bot': False},
            'chat': {'id': 1, 'type': 'private'}, **fields}})
    return response.json()['status']


def nonce(text):
    return re.search(r'Step: (\S+)', text)[1]


def test_deadhead_estimate_requires_confirmation_and_follows_endpoints(store, telegram):
    journey(store, 'next destination home; reposition 20; availability feasible')
    calls = []

    def lookup(pin, pickup):
        calls.append((pin, pickup))
        if pickup == 'Unmapped Dock':
            raise ValueError('No fixture route')
        return {(10.12, 20.65): Decimal('12.5'), (11.23, 21.23): Decimal('18')}.get(pin)

    conversation = OpeningConversation(store, offline_deadhead_lookup=lookup)
    with telegram(conversation) as (client, sent, worker):
        pin = {'latitude': 10.123456, 'longitude': 20.654321}
        assert post(client, 51, location=pin) == 'processed'
        assert not calls
        assert post(client, 52, text='pickup Fictional Dock; loaded 180') == 'processed'
        assert calls == [((10.12, 20.65), 'Fictional Dock')]
        assert 'miles to pickup: 12.5 [offline route estimate]' in sent[-1]
        assert '10.12' not in sent[-1] and '20.65' not in sent[-1]
        assert post(client, 53, text='/price') == 'invalid_update'
        assert post(client, 54, text=f'/confirm {nonce(sent[-1])}') == 'processed'
        assert post(client, 55, text='/price') == 'queued'
        assert worker.tick() == 'completed'
        assert 'Total miles: 212.5' in sent[-1]

        assert post(client, 56, location={'latitude': 11.234, 'longitude': 21.234}) == 'processed'
        assert 'miles to pickup: 18 [offline route estimate]' in sent[-1]
        old_nonce = nonce(sent[-1])
        assert post(client, 57, text=f'/confirm {old_nonce}') == 'processed'
        assert post(client, 58, text='pickup Unmapped Dock') == 'processed'
        assert 'miles to pickup: unknown' in sent[-1]
        assert 'Add missing mileage with these labels: deadhead' in sent[-1]
        assert post(client, 59, text=f'/confirm {old_nonce}') == 'processed'
        assert post(client, 60, text='/price') == 'invalid_update'

        assert post(client, 61, text='pickup Fictional Dock; loaded 180; deadhead 15') == 'processed'
        assert len(calls) == 3
        assert 'miles to pickup: 15 [carrier]' in sent[-1]
        assert 'miles after delivery: 20 [carrier]' in sent[-1]
        assert not store._opening.get(1, 1).confirmed


@pytest.mark.parametrize('estimate', [None, Decimal('NaN'), Decimal('-1'), Decimal('100001'), '12'])
def test_invalid_or_missing_estimate_keeps_deadhead_unknown(store, estimate):
    journey(store, 'pickup Fictional Dock; loaded 180')
    conversation = OpeningConversation(store, offline_deadhead_lookup=lambda *_: estimate)
    review = conversation.share_truck_pin(1, 1, (10.12, 20.65))
    assert 'miles to pickup: unknown' in review
    assert store._opening.get(1, 1).draft.facts.deadhead_miles is None


def test_forget_acknowledges_and_deletes_saved_test_profile(store, telegram):
    conversation = OpeningConversation(store)
    with telegram(conversation) as (client, sent, worker):
        assert post(client, 1, text='/start') == 'processed'
        assert post(client, 2, text=f'/reply {nonce(sent[-1])} remember') == 'processed'
        assert post(client, 3, text='cpm 1.25; target 2.00; minimum none; unit BOX-01') == 'processed'
        assert post(client, 4, text='save profile') == 'processed'
        assert store._db.execute('SELECT COUNT(*) FROM opening_profiles').fetchone() == (1,)

        assert post(client, 5, text='/forget') == 'queued'
        assert 'Consent withdrawn. Active session cleared' in sent[-1]
        assert worker.tick() == 'idle'
        assert store._db.execute('SELECT status FROM pilot_privacy').fetchone() == ('completed',)
        assert store._db.execute('SELECT COUNT(*) FROM opening_profiles').fetchone() == (0,)
