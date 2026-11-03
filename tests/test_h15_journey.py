"""Offline profile-first journey tests. Invented figures only, no live calls."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

import test_h15_opening_workflow as h15
from axle_hackathon.opening_telegram import (
    FIELD_LABELS, OpeningConversation, create_opening_app, parse_fields)
from axle_hackathon.opening_workflow import OpeningSessions, effective_compensation
from axle_hackathon.pilot_inbox import PilotInbox
from axle_hackathon.pilot_memory import MemoryPolicy
from axle_hackathon.pilot_runtime import OpeningWorker
from test_h13_memory import Clock
from test_h13_telegram import SECRET

BINDINGS = {(1, 1): 'owner'}
PROFILE = 'cpm 1.25; target 2.50; minimum 100; equipment 26ft box truck'


@pytest.fixture
def store(tmp_path):
    path = tmp_path / 'journey.sqlite3'
    policy = MemoryPolicy(version='test-journey-v1', processing_notice='Invented offline records only')
    inbox = PilotInbox(path, dict(BINDINGS), policy, clock=Clock())
    inbox._opening = OpeningSessions(dict(BINDINGS))
    yield inbox
    inbox.close()


def consent(store):
    conversation = OpeningConversation(store)
    conversation.handle(1, 1, '/start')
    nonce = store._conversation_states['owner']['nonce']
    conversation.handle(1, 1, f'/reply {nonce} session')
    return conversation


def profiled(store, message=PROFILE):
    conversation = consent(store)
    conversation.handle(1, 1, message)
    nonce = store._conversation_states['owner']['nonce']
    conversation.handle(1, 1, f'/confirm {nonce}')
    return conversation


def journey(store, trip='skip', update=50, limits=None):
    conversation = profiled(store)
    token = store._active['owner'].token
    h15.submit_shot(store, token, update=update, message=update)
    assert h15.worker(store, [], **(limits or {})).tick() == 'completed'
    conversation.handle(1, 1, trip)
    return conversation


def test_profile_required_before_screenshot(store):
    conversation = consent(store)
    with pytest.raises(KeyError):
        store._opening.get_profile(1, 1)
    assert store._conversation_states['owner']['step'] == 'profile'
    conversation.handle(1, 1, PROFILE)
    assert store._conversation_states['owner']['step'] == 'profile_review'
    with pytest.raises(KeyError):
        store._opening.get_profile(1, 1)
    nonce = store._conversation_states['owner']['nonce']
    conversation.handle(1, 1, f'/confirm {nonce}')
    profile = store._opening.get_profile(1, 1)
    assert (str(profile.operating_cpm), str(profile.target_all_mile_rpm),
            str(profile.minimum_job_charge)) == ('1.25', '2.50', '100')
    assert profile.equipment == '26ft box truck'
    assert store._conversation_states['owner']['step'] == 'photo'


def test_profile_minimum_required_and_itemized_rejected(store):
    conversation = consent(store)
    with pytest.raises(ValueError, match='Minimum charge must be supplied'):
        conversation.handle(1, 1, 'cpm 1.25; target 2.50')
    with pytest.raises(ValueError, match='normalization'):
        conversation.handle(1, 1, 'cpm itemized; minimum 0')
    assert store._conversation_states['owner']['step'] == 'profile'
    with pytest.raises(KeyError):
        store._opening.get_profile(1, 1)


def test_profile_reused_in_first_revision_with_sources(store):
    conversation = journey(store)
    snapshot = store._opening.get(1, 1)
    assert snapshot.revision == 1 and not snapshot.confirmed
    assert str(snapshot.pricing.operating_cpm) == '1.25'
    assert snapshot.sources['operating_cpm'] == 'profile'
    assert snapshot.sources['payout'] == 'screenshot'
    assert store._conversation_states['owner']['step'] == 'review'


def test_media_before_profile_gets_guidance_without_queue(store):
    sent = []
    app = create_opening_app(store, webhook_secret=SECRET, allowed_host='testserver',
        conversation=OpeningConversation(store), send=lambda c, t: sent.append(t) or True)
    with TestClient(app) as client:
        headers = {'X-Telegram-Bot-Api-Secret-Token': SECRET}
        def post(payload):
            posted = client.post('/telegram/webhook', json=payload, headers=headers)
            assert posted.status_code == 200
            return posted.json()['status']
        def command(text, update_id):
            return post(dict(update_id=update_id, message=dict(
                message_id=update_id, **{'from': dict(id=1, is_bot=False)},
                chat=dict(id=1, type='private'), text=text)))
        def photo(update_id):
            return post(dict(update_id=update_id, message=dict(
                message_id=update_id, **{'from': dict(id=1, is_bot=False)},
                chat=dict(id=1, type='private'),
                photo=[dict(file_id='f', file_unique_id='u', file_size=100)])))
        assert command('/start', 1) == 'processed'
        nonce = sent[-1].split('\nStep: ')[1].split('\n')[0]
        assert command(f'/reply {nonce} session', 2) == 'processed'
        assert photo(3) == 'processed'
        assert 'profile' in sent[-1].lower()
        assert photo(3) == 'duplicate'
    assert store._db.execute('SELECT COUNT(*) FROM pilot_updates').fetchone() == (3,)
    tables = {row[0] for row in store._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert 'pilot_budget' not in tables
    assert store._db.execute("SELECT COUNT(*) FROM pilot_updates WHERE action='screenshot'").fetchone() == (0,)


@pytest.mark.parametrize('text, expected', [
    ('target $2.50/mi', {'target_all_mile_rpm': '$2.50/mi'}),
    ('cpm: 1.25', {'operating_cpm': '1.25'}),
    ('minimum=none', {'minimum_job_charge': 'none'}),
    ('deadhead 40; reposition 20', {'deadhead_miles': '40', 'reposition_miles': '20'}),
    ('loaded miles 180\nhandling liftgate required',
     {'loaded_miles': '180', 'handling_note': 'liftgate required'}),
    ('counter 650', {'counter': '650'}),
])
def test_consolidated_labels_forms_units(text, expected):
    assert parse_fields(text, tuple(FIELD_LABELS)) == expected


@pytest.mark.parametrize('text', [
    'target 2.50; target 3.00',
    'turbo 5',
    'target',
    'cpm',
    '',
    'target 2.50; ' * 9,
])
def test_ambiguous_consolidated_input_rejected(text):
    with pytest.raises(ValueError):
        parse_fields(text, tuple(FIELD_LABELS))


def test_unit_values_applied_deterministically(store):
    conversation = journey(store)
    conversation.handle(1, 1, 'target $2.75 per mile')
    assert str(store._opening.get(1, 1).pricing.target_all_mile_rpm) == '2.75'
    with pytest.raises(ValueError):
        conversation.handle(1, 1, 'target 2.50 3.00')
    assert str(store._opening.get(1, 1).pricing.target_all_mile_rpm) == '2.75'


def test_trip_message_is_atomic(store):
    conversation = profiled(store)
    token = store._active['owner'].token
    h15.submit_shot(store, token)
    assert h15.worker(store, []).tick() == 'completed'
    with pytest.raises(ValueError):
        conversation.handle(1, 1, 'deadhead 40\navailability someday')
    assert store._opening.get(1, 1).revision == 1
    assert store._opening.get(1, 1).pricing.reposition_miles is None
    assert store._conversation_states['owner']['step'] == 'trip'


def test_est_mileage_proposes_without_converting(store):
    conversation = profiled(store)
    token = store._active['owner'].token
    noted = json.dumps(dict(status='UNCONFIRMED',
        facts=dict(payout=None, loaded_miles=None, deadhead_miles=None, weight_lbs=None),
        evidence=dict(payout='', loaded_miles='', deadhead_miles='', weight_lbs=''),
        issues=["Mileage labeled 'Est. mileage 480 mi' — verify before use."]))
    inner = h15.delegator(store, [], image_text=noted)
    worker = OpeningWorker(store, inner, lambda *_: True, global_limit=4, carrier_limit=4)
    h15.submit_shot(store, token)
    assert worker.tick() == 'completed'
    assert store._opening.get(1, 1).draft.facts.loaded_miles is None
    review = conversation.handle(1, 1, 'skip')
    assert 'Possible pickup-to-delivery interpretation (UNCONFIRMED, from note): 480 mi' in review
    assert 'loaded miles: unknown' in review
    resolved = conversation.handle(1, 1, 'loaded 480')
    assert str(store._opening.get(1, 1).draft.facts.loaded_miles) == '480'
    assert 'Possible pickup-to-delivery interpretation' not in resolved


def test_source_labels_and_note_retirement(store):
    conversation = journey(store, 'deadhead 40\navailability feasible')
    review = conversation.handle(1, 1, 'target 2.60')
    assert '[screenshot]' in review and '[profile]' in review and '[carrier]' in review
    assert 'target all-mile RPM: 2.60 [carrier]' in review
    assert 'deadhead miles: 40 [carrier]' in review
    assert 'operating CPM: 1.25 [profile]' in review
    assert 'payout: 420 [screenshot]' in review


def test_unresolved_warnings_kept_after_correction(store):
    conversation = profiled(store)
    token = store._active['owner'].token
    noted = json.dumps(dict(status='UNCONFIRMED',
        facts=dict(payout='420', loaded_miles='180', deadhead_miles=None, weight_lbs=None),
        evidence=dict(payout='Total payout $420', loaded_miles='Loaded 180 mi',
                      deadhead_miles='', weight_lbs=''),
        issues=['Payout figure partially obscured.', 'Schedule details not shown.']))
    inner = h15.delegator(store, [], image_text=noted)
    worker = OpeningWorker(store, inner, lambda *_: True, global_limit=4, carrier_limit=4)
    h15.submit_shot(store, token)
    assert worker.tick() == 'completed'
    conversation.handle(1, 1, 'skip')
    conversation.handle(1, 1, 'payout 430')
    issues = store._opening.get(1, 1).draft.issues
    assert not any('payout' in issue.lower() for issue in issues)
    assert any('schedule' in issue.lower() for issue in issues)


def test_numeric_counteroffer_requires_confirmation_before_reevaluation(store):
    conversation = journey(store, 'availability feasible')
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    assert store._opening.get(1, 1).confirmed
    conversation.handle(1, 1, 'counter 650')
    snapshot = store._opening.get(1, 1)
    assert str(snapshot.counter_offer) == '650' and not snapshot.confirmed
    assert snapshot.sources['counter_offer'] == 'carrier'
    assert effective_compensation(snapshot) == (snapshot.counter_offer, 'owner counteroffer')
    token = store._active['owner'].token
    with pytest.raises(ValueError):
        store.submit(1, 1, 70, 'opening', token=token, revision=snapshot.revision - 1, message_id=70)


def test_counter_text_stays_note_only(store):
    conversation = journey(store)
    conversation.handle(1, 1, 'counter call tuesday')
    snapshot = store._opening.get(1, 1)
    assert snapshot.counter_offer is None and snapshot.counter_note == 'call tuesday'
    assert effective_compensation(snapshot)[1] == 'posted offer'


def test_fictional_counteroffer_fixture_offline_rehearsal(store):
    path = Path(__file__).resolve().parents[1] / 'fixtures' / 'fictional_broker_counteroffer.json'
    fixture = json.loads(path.read_text())
    assert fixture['fictional'] is True and 'never' in fixture['warning'].lower()
    conversation = journey(store, 'availability feasible')
    conversation.handle(1, 1, f"counter {fixture['counteroffer_usd']}")
    snapshot = store._opening.get(1, 1)
    assert str(snapshot.counter_offer) == '1875.00'
    assert effective_compensation(snapshot)[1] == 'owner counteroffer'


def price_case(store, corrections, base=60):
    conversation = journey(store, 'availability feasible', update=base,
                           limits=dict(global_limit=10, carrier_limit=10))
    for correction in corrections:
        conversation.handle(1, 1, correction)
    snapshot = store._opening.get(1, 1)
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    token = store._active['owner'].token
    store.submit(1, 1, base + 1, 'opening', token=token, revision=snapshot.revision,
                 message_id=base + 1)
    sent = []
    inner = h15.delegator(store, [], image_text=h15.draft_text())
    worker = OpeningWorker(store, inner, lambda c, t: sent.append(t) or True,
                           global_limit=10, carrier_limit=10)
    assert worker.tick() == 'completed'
    return sent[0]


def test_offer_negotiate_on_gap(store):
    text = price_case(store, ('target 2.50', 'cpm 1.25', 'minimum 100', 'reposition 20'))
    assert 'Offer evaluation' in text and 'NEGOTIATE' in text
    assert 'Revenue gap to target: $180.00' in text
    assert 'Estimated operating surplus: $120.00' in text
    assert 'DRAFT — NOT SENT' in text and 'never a booking' in text


def test_offer_accept_and_minimum_floor(store):
    text = price_case(store, ('target 2.50', 'cpm 1.25', 'minimum 100', 'reposition 20',
                              'counter 650'))
    assert ': ACCEPT' in text
    assert 'Estimated operating cost: $300.00' in text
    assert 'Target revenue: $600.00' in text
    assert 'Broker wording' not in text
    negotiate = price_case(store, ('target 2.50', 'cpm 1.25', 'minimum 100', 'reposition 20'),
                           base=70)
    broker = negotiate.split('Broker wording')[1]
    assert '300.00' not in broker and '1.25' not in broker and 'minimum' not in broker.lower()
    floor = price_case(store, ('target 1.00', 'cpm 1.25', 'minimum 400', 'reposition 20',
                               'counter 350'), base=80)
    assert 'NEGOTIATE' in floor
    assert 'I can do it at $400.00' in floor.split('Broker wording')[1]


def test_unknown_segments_stay_unknown_in_evaluation(store):
    missing_repo = price_case(store, ('target 2.50', 'cpm 1.25', 'minimum 100',
                                      'counter 900'))
    assert 'NEED_MORE_INFORMATION' in missing_repo
    assert 'reposition_miles' in missing_repo
    missing_dh = price_case(store, ('target 2.50', 'cpm 1.25', 'minimum 100',
                                    'reposition 20', 'deadhead unknown', 'counter 900'),
                            base=70)
    assert 'NEED_MORE_INFORMATION' in missing_dh and 'deadhead_miles' in missing_dh


def test_explicit_zero_segments_accepted(store):
    text = price_case(store, ('target 2.50', 'cpm 1.25', 'minimum 100', 'deadhead 0',
                              'reposition 0', 'counter 650'))
    assert ': ACCEPT' in text
    assert 'Total miles: 180' in text


def test_negotiate_without_consistent_ask_omits_number(store):
    text = price_case(store, ('target 1.00', 'cpm 1.25', 'minimum 100', 'reposition 20',
                              'counter 200'))
    assert 'NEGOTIATE' in text
    assert 'I can do it at' not in text
    assert 'before naming a price' in text and 'carrier review' in text
    assert '300.00' not in text.split('Broker wording')[1]


def test_missing_feasibility_blocks_accept(store):
    conversation = journey(store)
    for correction in ('target 2.50', 'cpm 1.25', 'minimum 100', 'reposition 20',
                       'counter 900'):
        conversation.handle(1, 1, correction)
    snapshot = store._opening.get(1, 1)
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    token = store._active['owner'].token
    store.submit(1, 1, 82, 'opening', token=token, revision=snapshot.revision, message_id=82)
    sent = []
    inner = h15.delegator(store, [], image_text=h15.draft_text())
    worker = OpeningWorker(store, inner, lambda c, t: sent.append(t) or True,
                           global_limit=4, carrier_limit=4)
    assert worker.tick() == 'completed'
    assert 'NEED_MORE_INFORMATION' in sent[0] and 'schedule_feasibility' in sent[0]


def test_blocked_availability_declines(store):
    conversation = journey(store, 'availability blocked')
    for correction in ('target 2.50', 'cpm 1.25', 'minimum 100', 'reposition 20',
                       'counter 900'):
        conversation.handle(1, 1, correction)
    snapshot = store._opening.get(1, 1)
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    token = store._active['owner'].token
    store.submit(1, 1, 83, 'opening', token=token, revision=snapshot.revision, message_id=83)
    sent = []
    inner = h15.delegator(store, [], image_text=h15.draft_text())
    worker = OpeningWorker(store, inner, lambda c, t: sent.append(t) or True,
                           global_limit=4, carrier_limit=4)
    assert worker.tick() == 'completed'
    assert 'DECLINE' in sent[0]


def test_opening_bid_without_compensation_and_guidance(store):
    conversation = journey(store, 'availability feasible')
    for correction in ('payout unknown', 'target 2.50', 'cpm 1.25', 'minimum 100', 'reposition 20'):
        conversation.handle(1, 1, correction)
    snapshot = store._opening.get(1, 1)
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    token = store._active['owner'].token
    store.submit(1, 1, 84, 'opening', token=token, revision=snapshot.revision, message_id=84)
    sent = []
    inner = h15.delegator(store, [], image_text=h15.draft_text())
    worker = OpeningWorker(store, inner, lambda c, t: sent.append(t) or True,
                           global_limit=4, carrier_limit=4)
    assert worker.tick() == 'completed'
    assert 'Preliminary opening price' in sent[0] and 'Opening bid: $600.00' in sent[0]
    assert 'Negotiation guidance (internal):' in sent[0]
    assert 'DRAFT — NOT SENT' in sent[0]
    broker = sent[0].split('Broker wording')[1]
    assert '300.00' not in broker and '600.00' not in broker.split('open at')[0]


def test_equipment_correction_updates_profile_and_invalidates(store):
    conversation = journey(store)
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    assert store._opening.get(1, 1).confirmed
    conversation.handle(1, 1, 'equipment 53ft reefer')
    snapshot = store._opening.get(1, 1)
    assert not snapshot.confirmed and snapshot.revision == 2
    assert store._opening.get_profile(1, 1).equipment == '53ft reefer'


def test_session_reuse_across_screenshots(store):
    conversation = journey(store, 'deadhead 40\navailability feasible')
    token = store._active['owner'].token
    h15.submit_shot(store, token, update=55, message=55)
    assert h15.worker(store, []).tick() == 'completed'
    snapshot = store._opening.get(1, 1)
    assert snapshot.revision == 3 and not snapshot.confirmed
    assert str(snapshot.pricing.target_all_mile_rpm) == '2.50'
    assert snapshot.trip.availability == 'feasible'
    assert snapshot.sources['target_all_mile_rpm'] == 'profile'


def test_stage_trailers_replace_generic_footer(store):
    conversation = consent(store)
    memory = store._conversation_states['owner']
    assert memory['step'] == 'profile'
    profile_reply = conversation.handle(1, 1, PROFILE)
    assert '/reply STEP answer' not in profile_reply
    nonce = store._conversation_states['owner']['nonce']
    photo_reply = conversation.handle(1, 1, f'/confirm {nonce}')
    assert '\nStep: ' not in photo_reply
    token = store._active['owner'].token
    h15.submit_shot(store, token)
    assert h15.worker(store, []).tick() == 'completed'
    trip_reply = conversation.handle(1, 1, 'skip')
    assert '/confirm STEP |' in trip_reply and '/reply STEP answer' not in trip_reply
    nonce = store._conversation_states['owner']['nonce']
    confirmed_reply = conversation.handle(1, 1, f'/confirm {nonce}')
    assert '/price |' in confirmed_reply and '/reply STEP answer' not in confirmed_reply


def test_stale_nonce_cross_owner_and_expiry(store):
    conversation = journey(store)
    flow = store._conversation_states['owner']
    with pytest.raises(ValueError, match='Stale conversation step'):
        conversation.handle(1, 1, f"/confirm stale-nonce-value")
    assert store._opening.get(1, 1).revision == flow['revision']
    with pytest.raises(PermissionError):
        conversation.handle(2, 1, 'target 9.99')
    with pytest.raises(PermissionError):
        conversation.handle(1, 2, 'target 9.99')


def test_refresh_and_prompts_spend_nothing(store):
    journey(store)
    before = store._opening.get(1, 1).revision
    conversation = OpeningConversation(store)
    conversation.handle(1, 1, '/refresh')
    conversation.handle(1, 1, '/refresh')
    assert store._opening.get(1, 1).revision == before
    assert store._db.execute('SELECT SUM(attempts) FROM pilot_budget').fetchone() == (1,)


def test_forget_clears_profile_and_session(store):
    journey(store, 'deadhead 40')
    assert store._opening.get_profile(1, 1).equipment == '26ft box truck'
    store.forget(1, 1)
    with pytest.raises(KeyError):
        store._opening.get_profile(1, 1)
    with pytest.raises(KeyError):
        store._opening.get(1, 1)


def test_expired_consent_blocks_profile_confirm(tmp_path):
    from axle_hackathon.pilot_memory import MemoryPolicy
    clock = Clock()
    policy = MemoryPolicy(version='test-journey-v1', processing_notice='Invented offline records only',
                          session_seconds=60)
    inbox = PilotInbox(tmp_path / 'expiry.sqlite3', dict(BINDINGS), policy, clock=clock)
    inbox._opening = OpeningSessions(dict(BINDINGS))
    try:
        conversation = OpeningConversation(inbox)
        conversation.handle(1, 1, '/start')
        nonce = inbox._conversation_states['owner']['nonce']
        conversation.handle(1, 1, f'/reply {nonce} session')
        conversation.handle(1, 1, PROFILE)
        clock.advance(61)
        nonce = inbox._conversation_states['owner']['nonce']
        with pytest.raises(PermissionError):
            conversation.handle(1, 1, f'/confirm {nonce}')
        with pytest.raises(KeyError):
            inbox._opening.get_profile(1, 1)
    finally:
        inbox.close()
