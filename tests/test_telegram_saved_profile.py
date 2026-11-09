"""Offline saved truck profile journey, privacy and restart regression tests."""
import sqlite3
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from axle_hackathon.opening_profile_store import OpeningProfileStore
from axle_hackathon.opening_telegram import OpeningConversation, create_opening_app
from axle_hackathon.opening_workflow import OpeningProfile, OpeningSessions
from axle_hackathon.pilot_inbox import PilotInbox
from axle_hackathon.pilot_memory import MemoryPolicy
from test_h13_memory import Clock
from test_h13_telegram import SECRET

BINDINGS = {(1, 1): 'a', (2, 2): 'b'}
PROFILE = ('cpm 1.25; target 2; minimum none; equipment 26ft box truck; '
           'dot 1234567; mc MC-123456; unit BOX-01; capabilities liftgate, pallet jack; '
           'arrangement owned; home base Fictional yard')


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / 'owner.sqlite3'
    policy = MemoryPolicy(version='saved-truck-test', processing_notice='Invented records only',
                          session_seconds=60, profile_seconds=120)
    clock = Clock()
    inbox = open_inbox(path, policy, clock)
    yield inbox, path, policy, clock
    inbox.close()


def open_inbox(path, policy, clock):
    inbox = PilotInbox(path, BINDINGS, policy, clock=clock)
    inbox._opening = OpeningSessions(BINDINGS)
    return inbox


def begin(inbox, user=1, choice='remember'):
    chat = OpeningConversation(inbox)
    chat.handle(user, user, '/start')
    flow = inbox._conversation_states[BINDINGS[(user, user)]]
    answer = chat.handle(user, user, f'/reply {flow["nonce"]} {choice}')
    return chat, answer


def reviewed(inbox, user=1, choice='remember'):
    chat, _ = begin(inbox, user, choice)
    chat.handle(user, user, PROFILE)
    return chat


def token(inbox, user=1):
    return inbox._active[BINDINGS[(user, user)]].token


def load(inbox, user=1):
    return OpeningProfileStore(inbox).load(user, user, token(inbox, user))


def test_explicit_save_only_with_review_and_storage_consent(setup):
    inbox, *_ = setup
    chat = reviewed(inbox, choice='session')
    assert inbox._db.execute('SELECT count(*) FROM opening_profiles').fetchone() == (0,)
    with pytest.raises(PermissionError):
        chat.handle(1, 1, 'save profile')
    flow = inbox._conversation_states['a']
    chat.handle(1, 1, '/confirm ' + flow['nonce'])
    assert inbox._db.execute('SELECT count(*) FROM opening_profiles').fetchone() == (0,)
    chat = reviewed(inbox)
    assert inbox._db.execute('SELECT count(*) FROM opening_profiles').fetchone() == (0,)
    result = chat.handle(1, 1, 'save profile')
    assert 'saved and confirmed' in result
    saved = load(inbox)
    assert saved.profile.usdot == '1234567'
    assert saved.profile.mc == '123456'
    assert saved.profile.unit_number == 'BOX-01'
    assert saved.profile.arrangement == 'owned'
    assert 'unverified' in chat._render_profile(saved.profile)
    assert 'not a confirmed next destination' in chat._render_profile(saved.profile)
    assert saved.profile == inbox._opening.get_profile(1, 1)
    assert inbox._db.execute('SELECT count(*) FROM opening_profiles').fetchone() == (1,)


def test_restart_reloads_as_editable_draft_with_new_consent(setup):
    inbox, path, policy, clock = setup
    chat = reviewed(inbox)
    chat.handle(1, 1, 'save profile')
    old_token = token(inbox)
    inbox.close()
    other = open_inbox(path, policy, clock)
    try:
        with pytest.raises(PermissionError):
            OpeningProfileStore(other).load(1, 1, old_token)
        chat, answer = begin(other)
        assert 'loaded as a draft' in answer
        assert other._conversation_states['a']['step'] == 'profile_review'
        with pytest.raises(KeyError):
            other._opening.get_profile(1, 1)
        chat.handle(1, 1, 'edit profile')
        chat.handle(1, 1, 'cpm 1.50; unit BOX-02')
        assert load(other).profile.operating_cpm == Decimal('1.25')
        chat.handle(1, 1, 'save profile')
        assert load(other).profile.operating_cpm == Decimal('1.50')
        assert load(other).profile.unit_number == 'BOX-02'
        assert load(other).profile.usdot == '1234567'
        with pytest.raises(KeyError):
            other._opening.get(1, 1)  # no opportunity or old confirmation restored
    finally:
        other.close()


def test_session_only_and_forget_delete_saved_truck(setup):
    inbox, *_ = setup
    chat = reviewed(inbox)
    chat.handle(1, 1, 'save profile')
    begin(inbox, choice='session')
    assert inbox._db.execute('SELECT count(*) FROM opening_profiles').fetchone() == (0,)
    chat = reviewed(inbox)
    chat.handle(1, 1, 'save profile')
    inbox.forget(1, 1)
    assert inbox._db.execute('SELECT count(*) FROM opening_profiles').fetchone() == (0,)
    assert 'a' not in inbox._active


def test_expiry_access_and_maintenance(setup):
    inbox, _, _, clock = setup
    reviewed(inbox).handle(1, 1, 'save profile')
    clock.advance(121)
    chat, answer = begin(inbox)
    assert 'loaded as a draft' not in answer
    assert load(inbox) is None
    chat.handle(1, 1, PROFILE)
    chat.handle(1, 1, 'save profile')
    clock.advance(121)
    inbox.purge_expired()
    assert inbox._db.execute('SELECT count(*) FROM opening_profiles').fetchone() == (0,)


def test_carrier_isolation_and_dot_never_selects_tenant(setup):
    inbox, *_ = setup
    reviewed(inbox).handle(1, 1, 'save profile')
    chat, answer = begin(inbox, user=2)
    assert 'BOX-01' not in answer
    assert load(inbox, 2) is None
    chat.handle(2, 2, PROFILE.replace('BOX-01', 'BOX-OTHER'))
    chat.handle(2, 2, 'save profile')
    assert load(inbox).profile.unit_number == 'BOX-01'
    assert load(inbox, 2).profile.unit_number == 'BOX-OTHER'
    with pytest.raises(PermissionError):
        OpeningProfileStore(inbox).load(1, 2, token(inbox))
    with pytest.raises(PermissionError):
        OpeningProfileStore(inbox).load(2, 2, token(inbox))
    inbox.forget(1, 1)
    assert load(inbox, 2).profile.unit_number == 'BOX-OTHER'


def test_stale_review_and_storage_version_rejected(setup):
    inbox, *_ = setup
    chat = reviewed(inbox)
    flow = inbox._conversation_states['a']
    old_nonce = flow['nonce']
    chat.handle(1, 1, 'cpm 1.5')
    with pytest.raises(ValueError, match='Stale'):
        chat.handle(1, 1, '/save_profile ' + old_nonce)
    inbox._opening.set_profile(1, 1, OpeningProfile(minimum_job_charge=0))
    with pytest.raises(ValueError, match='changed'):
        chat.handle(1, 1, 'save profile')
    chat.handle(1, 1, 'cpm 1.75')
    chat.handle(1, 1, 'save profile')
    chat, _ = begin(inbox)
    old = load(inbox)
    with inbox._db:
        inbox._db.execute("UPDATE opening_profiles SET version='changed' WHERE carrier='a'")
    with pytest.raises(ValueError, match='Stale saved'):
        chat.handle(1, 1, 'save profile')
    assert load(inbox).profile == old.profile


def test_save_failure_leaves_review_recoverable_and_session_unconfirmed(setup):
    inbox, *_ = setup
    chat = reviewed(inbox)
    inbox._db.execute("CREATE TRIGGER fail_profile BEFORE INSERT ON opening_profiles "
                      "BEGIN SELECT RAISE(FAIL, 'invented failure'); END")
    inbox._db.commit()
    with pytest.raises(sqlite3.DatabaseError):
        chat.handle(1, 1, 'save profile')
    assert inbox._conversation_states['a']['step'] == 'profile_review'
    assert load(inbox) is None
    with pytest.raises(KeyError):
        inbox._opening.get_profile(1, 1)
    inbox._db.execute('DROP TRIGGER fail_profile')
    inbox._db.commit()
    chat.handle(1, 1, 'save profile')
    assert load(inbox) is not None


def test_webhook_duplicate_save_delivers_once(setup):
    inbox, *_ = setup
    chat = reviewed(inbox)
    sent = []
    app = create_opening_app(inbox, webhook_secret=SECRET, allowed_host='testserver',
        conversation=chat, send=lambda c, t: sent.append(t) or True)
    payload = dict(update_id=1, message=dict(message_id=1,
        **{'from': dict(id=1, is_bot=False)}, chat=dict(id=1, type='private'), text='save profile'))
    with TestClient(app) as client:
        headers = {'X-Telegram-Bot-Api-Secret-Token': SECRET}
        first = client.post('/telegram/webhook', json=payload, headers=headers)
        version = load(inbox).version
        second = client.post('/telegram/webhook', json=payload, headers=headers)
    assert first.json()['status'] == 'processed'
    assert second.json()['status'] == 'duplicate'
    assert load(inbox).version == version
    assert len(sent) == 1


@pytest.mark.parametrize('field', ['dot -1', 'dot 0', 'dot abc', 'dot 123456789',
                                   'mc MC-nope', 'arrangement borrowed'])
def test_invalid_identity_never_creates_saved_record(setup, field):
    inbox, *_ = setup
    chat, _ = begin(inbox)
    with pytest.raises(ValueError):
        chat.handle(1, 1, 'minimum none; ' + field)
    assert load(inbox) is None


def test_nickname_without_unit_is_supported(setup):
    inbox, *_ = setup
    chat, _ = begin(inbox)
    chat.handle(1, 1, 'minimum none; nickname Blue truck; mc n/a')
    chat.handle(1, 1, 'save profile')
    assert load(inbox).profile.truck_nickname == 'Blue truck'
    assert load(inbox).profile.unit_number is None
    assert load(inbox).profile.mc is None


def test_pending_forget_survives_restart_and_blocks_profile_reuse(setup):
    inbox, path, policy, clock = setup
    reviewed(inbox).handle(1, 1, 'save profile')
    inbox.submit(1, 1, 90, 'forget', message_id=90)
    inbox.close()
    other = open_inbox(path, policy, clock)
    try:
        # Consent services a pending privacy deletion before any saved-profile read.
        _, answer = begin(other)
        assert 'BOX-01' not in answer
        assert load(other) is None
        assert other._db.execute('SELECT count(*) FROM opening_profiles').fetchone() == (0,)
    finally:
        other.close()


def test_expired_consent_cannot_save_or_load(setup):
    inbox, _, _, clock = setup
    chat = reviewed(inbox)
    stale = token(inbox)
    clock.advance(61)
    with pytest.raises(PermissionError):
        chat.handle(1, 1, 'save profile')
    with pytest.raises(PermissionError):
        OpeningProfileStore(inbox).load(1, 1, stale)
    assert inbox._db.execute('SELECT count(*) FROM opening_profiles').fetchone() == (0,)


def test_default_host_is_chat_only_and_never_contacts_provider_for_setup(setup, monkeypatch, tmp_path):
    import httpx
    import axle_hackathon.pilot_factory as factory
    from test_h13_transports import TOKEN, response
    requests = []
    def handle(request):
        import json
        requests.append(request)
        assert request.url.host == 'api.telegram.org'
        assert 'reply_markup' not in json.loads(request.content)
        return response(200, json_value={'ok': True, 'result': {
            'message_id': len(requests), 'chat': {'id': 1, 'type': 'private'}}})
    monkeypatch.setattr(httpx, 'HTTPTransport', lambda **_: httpx.MockTransport(handle))
    host = factory.build_opening_host(tmp_path / 'chat-only.sqlite3', {(1, 1): 'owner'},
        MemoryPolicy(version='chat-only-test', processing_notice='Invented only'),
        provider_key='invented-key', bot_token=TOKEN, webhook_secret=SECRET,
        allowed_host='testserver', global_limit=4, carrier_limit=4)
    with TestClient(host) as client:
        for path in ('/miniapp/', '/miniapp/app.js', '/miniapp/logo.png', '/miniapp/api/state'):
            assert client.get(path).status_code == 404
        payload = dict(update_id=1, message=dict(message_id=1,
            **{'from': dict(id=1, is_bot=False)}, chat=dict(id=1, type='private'), text='/start'))
        assert client.post('/telegram/webhook', json=payload,
            headers={'X-Telegram-Bot-Api-Secret-Token': SECRET}).json()['status'] == 'processed'
    assert len(requests) == 1
    assert all(host.last_shutdown.values())


def test_view_profile_keeps_workflow_and_saved_version(setup):
    inbox, *_ = setup
    chat = reviewed(inbox)
    chat.handle(1, 1, 'save profile')
    before = load(inbox).version
    assert inbox._conversation_states['a']['step'] == 'photo'
    shown = chat.handle(1, 1, '/profile')
    assert 'BOX-01' in shown
    assert 'Starting again clears the current load session' in shown
    assert inbox._conversation_states['a']['step'] == 'photo'
    assert load(inbox).version == before


def test_failed_profile_delete_keeps_privacy_intent_and_blocks_reuse(setup):
    inbox, *_ = setup
    reviewed(inbox).handle(1, 1, 'save profile')
    inbox._db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON opening_profiles "
                      "BEGIN SELECT RAISE(FAIL, 'invented deletion failure'); END")
    inbox._db.commit()
    with pytest.raises(sqlite3.DatabaseError):
        inbox.forget(1, 1)
    assert 'a' not in inbox._active
    assert inbox._db.execute('SELECT carrier FROM pilot_deletions').fetchall() == [('a',)]
    with pytest.raises(sqlite3.DatabaseError):
        begin(inbox)
    assert 'a' not in inbox._active
    inbox._db.execute('DROP TRIGGER fail_delete')
    inbox._db.commit()
    _, answer = begin(inbox)
    assert 'BOX-01' not in answer
    assert load(inbox) is None


def test_second_opportunity_reuses_truck_and_requires_fresh_trip(setup):
    from test_h15_opening_workflow import submit_shot, worker

    inbox, *_ = setup
    chat = reviewed(inbox)
    chat.handle(1, 1, 'save profile')
    saved = load(inbox)
    submit_shot(inbox, token(inbox))
    assert worker(inbox, []).tick() == 'completed'
    chat.handle(1, 1, 'next destination yard; reposition 20; availability blocked; '
                      'duration 6 hours; handling liftgate; payout goal 480; counter 650')
    chat.handle(1, 1, 'counter waiting for revised terms')
    first = inbox._opening.get(1, 1)
    inbox._opening.confirm(1, 1, first.revision)

    submit_shot(inbox, token(inbox), update=60, message=60)
    assert worker(inbox, []).tick() == 'completed'
    second = inbox._opening.get(1, 1)
    assert not second.confirmed
    assert inbox._conversation_states['a']['step'] == 'trip'
    assert second.trip.next_destination is None
    assert second.trip.availability == 'unknown'
    assert second.trip.duration_note is second.trip.handling_note is None
    assert second.counter_offer is second.counter_note is None
    assert second.pricing.reposition_miles is second.pricing.target_total_payout is None
    assert second.pricing.target_all_mile_rpm == saved.profile.target_all_mile_rpm
    assert inbox._opening.get_profile(1, 1) == saved.profile
    assert load(inbox) == saved

    chat.handle(1, 1, 'next destination home; deadhead 30; reposition 35; availability feasible')
    home = inbox._opening.get(1, 1)
    assert home.trip.next_destination == 'home'
    inbox._opening.confirm(1, 1, home.revision)
    result = inbox._opening.evaluate(1, 1, home.revision)
    assert result['total_miles'] == '245'
    assert result['estimated_operating_cost'] == '306.25'
    assert result['target_revenue'] == '490.00'

    chat.handle(1, 1, 'next destination yard')
    changed = inbox._opening.get(1, 1)
    assert not changed.confirmed
    assert changed.pricing.reposition_miles is None
