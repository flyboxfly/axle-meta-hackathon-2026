"""Offline regression for pricing rejection followed by normal chat commands."""
from decimal import Decimal

from axle_hackathon.opening_telegram import OpeningConversation
from test_h15_journey import journey
from test_h13_telegram import SECRET
from test_h15_opening_workflow import store
from test_telegram_deadhead_estimates import nonce, post, telegram


def test_unconfirmed_price_acknowledged_once_and_chat_continues(store, telegram):
    conversation = journey(store, 'deadhead 40; reposition 20; availability feasible')
    before = store._opening.get(1, 1)
    with telegram(conversation) as (client, sent, worker):
        response = client.post('/telegram/webhook',
            headers={'X-Telegram-Bot-Api-Secret-Token': SECRET},
            json={'update_id': 51, 'message': {
                'message_id': 51, 'from': {'id': 1, 'is_bot': False},
                'chat': {'id': 1, 'type': 'private'}, 'text': '/price'}})
        assert response.status_code == 200
        assert response.json()['status'] == 'processed'
        assert 'Confirm the current draft before requesting pricing.' in sent[-1]
        assert store._opening.get(1, 1) == before
        assert worker.tick() == 'idle'
        assert post(client, 51, text='/price') == 'duplicate'
        assert len(sent) == 1
        assert post(client, 52, text='/refresh') == 'processed'
        assert post(client, 53, text=f'/edit {nonce(sent[-1])} deadhead 45') == 'processed'
        assert 'miles to pickup: 45 [carrier]' in sent[-1]
        assert not store._opening.get(1, 1).confirmed
        assert post(client, 54, text=f'/confirm {nonce(sent[-1])}') == 'processed'
        assert post(client, 51, text='/price') == 'duplicate'
        assert worker.tick() == 'idle'
        assert post(client, 55, text='/price') == 'queued'
        assert worker.tick() == 'completed'


def test_estimate_display_rounds_without_changing_stored_miles(store):
    journey(store, 'pickup Fictional Dock; loaded 180')
    miles = Decimal('59.23096615763938598584267876')
    conversation = OpeningConversation(store, offline_deadhead_lookup=lambda *_: miles)
    review = conversation.share_truck_pin(1, 1, (10.12, 20.65))
    assert 'miles to pickup: 59.23 [offline route estimate]' in review
    assert store._opening.get(1, 1).draft.facts.deadhead_miles == miles
