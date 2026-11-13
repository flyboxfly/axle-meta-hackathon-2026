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
    def connect(conversation, **options):
        sent = []

        def send(chat, text):
            assert chat == 1
            sent.append(text)
            return True

        app = create_opening_app(store, webhook_secret=SECRET, allowed_host='testserver',
                                 conversation=conversation, send=send, **options)
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
        assert 'miles to pickup: 12.50 [offline route estimate]' in sent[-1]
        assert '10.12' not in sent[-1] and '20.65' not in sent[-1]
        assert post(client, 53, text='/price') == 'processed'
        assert post(client, 54, text=f'/confirm {nonce(sent[-1])}') == 'processed'
        assert post(client, 55, text='/price') == 'queued'
        assert worker.tick() == 'completed'
        assert 'Total miles: 212.5' in sent[-1]

        assert post(client, 56, location={'latitude': 11.234, 'longitude': 21.234}) == 'processed'
        assert 'miles to pickup: 18.00 [offline route estimate]' in sent[-1]
        old_nonce = nonce(sent[-1])
        assert post(client, 57, text=f'/confirm {old_nonce}') == 'processed'
        assert post(client, 58, text='pickup Unmapped Dock') == 'processed'
        assert 'miles to pickup: unknown' in sent[-1]
        assert 'Add missing mileage with these labels: deadhead' in sent[-1]
        assert post(client, 59, text=f'/confirm {old_nonce}') == 'processed'
        assert post(client, 60, text='/price') == 'processed'

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


@pytest.mark.parametrize("manual_edit", [False, True])
def test_tomtom_requires_opt_in_and_cannot_overwrite_manual_miles(store, telegram, manual_edit):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from axle_hackathon.opening_tomtom import DeadheadTruck, PickupCandidate, RoutePoint

    conversation = journey(store, 'pickup Fictional Dock; loaded 180')
    entered, release = Event(), Event()
    calls = []

    class FakeTomTom:
        async def find_pickups(self, address):
            calls.append(address)
            return (
                PickupCandidate(address="1 Fictional Dock", point=RoutePoint(latitude=40, longitude=-74)),
                PickupCandidate(address="2 Fictional Dock", point=RoutePoint(latitude=41, longitude=-75)),
            )

        async def estimate_miles(self, origin, pickup, truck):
            import asyncio
            calls.append((origin, pickup, truck))
            entered.set()
            if manual_edit:
                assert await asyncio.to_thread(release.wait, 5)
            return Decimal("18.5")

    truck = DeadheadTruck(height_m="3.8", width_m="2.6", length_m="10.2", weight_kg=7500)
    carrier = store._carrier(1, 1)
    with telegram(conversation, deadhead_adapter=FakeTomTom(),
                  deadhead_trucks={carrier: truck}) as (client, sent, _):
        assert post(client, 51, location={"latitude": 40.1234, "longitude": -74.1234}) == 'processed'
        assert post(client, 52, text="/deadhead") == 'processed'
        assert calls == []
        assert "TomTom receives the pickup address" in sent[-1]
        search = re.search(r'(/deadhead \S+ search)', sent[-1])[1]
        assert post(client, 53, text=search) == 'processed'
        assert calls == ["Fictional Dock"]
        assert post(client, 53, text=search) == 'duplicate'
        assert "2. 2 Fictional Dock" in sent[-1]
        select = re.search(r'(/deadhead \S+) NUMBER', sent[-1])[1] + ' 2'
        if manual_edit:
            with ThreadPoolExecutor() as pool:
                request = pool.submit(post, client, 54, text=select)
                try:
                    assert entered.wait(5)
                    assert post(client, 55, text="deadhead 9") == 'processed'
                finally:
                    release.set()
                assert request.result(timeout=5) == 'stale'
        else:
            assert post(client, 54, text=select) == 'processed'
            assert "18.50 [TomTom estimate]" in sent[-1]
        assert calls[1][0].latitude == Decimal("40.12")
        assert calls[1][1].address == "2 Fictional Dock"
        assert len(calls) == 2
        snapshot = conversation.opening.get(1, 1)
        assert snapshot.draft.facts.deadhead_miles == Decimal("9" if manual_edit else "18.5")
        assert not snapshot.confirmed

        if not manual_edit:
            assert post(client, 55, text='/price') == 'processed'
            assert 'Confirm the current draft before requesting pricing.' in sent[-1]
            assert post(client, 55, text='/price') == 'duplicate'
            assert post(client, 56, text='/refresh') == 'processed'
            assert '18.50 [TomTom estimate]' in sent[-1]
            assert post(client, 57, text=f'/edit {nonce(sent[-1])} pickup New Fictional Dock') == 'processed'
            changed = conversation.opening.get(1, 1)
            assert changed.draft.facts.deadhead_miles is None
            assert changed.draft.facts.loaded_miles is None
            assert post(client, 58, text=f'/edit {nonce(sent[-1])} deadhead 40') == 'processed'
            assert 'miles to pickup: 40 [carrier]' in sent[-1]
            assert len(calls) == 2


@pytest.mark.parametrize("endpoint", ["delivery", "next destination"])
def test_tomtom_reposition_to_home_requires_both_matches(store, telegram, endpoint):
    from axle_hackathon.opening_tomtom import DeadheadTruck, PickupCandidate, RoutePoint

    conversation = journey(store, 'delivery 20 Fictional Dock; next destination home')
    profile = conversation.opening.get_profile(1, 1)
    conversation.opening.set_profile(1, 1, profile.model_copy(
        update={"home_base": "30 Fictional Yard"}))
    lookups, routes = [], []

    class Routing:
        async def find_pickups(self, address):
            lookups.append(address)
            return (PickupCandidate(address=address, point=RoutePoint(
                latitude=40 + len(lookups), longitude=-74)),)

        async def estimate_miles(self, origin, destination, truck):
            routes.append((origin.latitude, destination.point.latitude))
            return Decimal("15.234")

    truck = DeadheadTruck(height_m="3.8", width_m="2.6", length_m="10.2", weight_kg=7500)
    with telegram(conversation, deadhead_adapter=Routing(),
                  deadhead_trucks={store._carrier(1, 1): truck}) as (client, sent, _):
        assert post(client, 51, text="/reposition") == "processed"
        assert "Next stop: 30 Fictional Yard" in sent[-1]
        assert not lookups
        search = re.search(r"(/reposition \S+ search)", sent[-1])[1]
        assert post(client, 52, text=search) == "processed"
        assert lookups == ["20 Fictional Dock", "30 Fictional Yard"]
        assert not routes
        select = re.search(r"(/reposition \S+) DELIVERY_NUMBER", sent[-1])[1]
        assert post(client, 53, text=select + " 1 1") == "processed"
        assert routes == [(41, 42)]
        assert "miles after delivery: 15.23 [TomTom estimate]" in sent[-1]
        snapshot = conversation.opening.get(1, 1)
        assert snapshot.pricing.reposition_miles == Decimal("15.234")
        assert not snapshot.confirmed
        assert post(client, 54, text=f"/edit {nonce(sent[-1])} {endpoint} New Fictional Site") == "processed"
        assert "miles after delivery: unknown" in sent[-1]
        assert post(client, 55, text=f"/edit {nonce(sent[-1])} reposition 0") == "processed"
        assert "miles after delivery: 0 [carrier]" in sent[-1]
