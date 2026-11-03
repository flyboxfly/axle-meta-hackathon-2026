"""Offline Mini App auth/journey tests. Invented figures only, no live calls."""
import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import httpx
import pytest
from fastapi.testclient import TestClient

import test_h15_opening_workflow as h15
from axle_hackathon.opening_miniapp import resolve_owner, verify_init_data
from axle_hackathon.opening_telegram import OpeningConversation, create_opening_app
from axle_hackathon.opening_workflow import OpeningSessions
from axle_hackathon.pilot_inbox import PilotInbox
from axle_hackathon.pilot_memory import MemoryPolicy
from axle_hackathon.pilot_runtime import OpeningWorker
from axle_hackathon.pilot_transports import TelegramWebAppButton
from test_h13_memory import Clock
from test_h13_telegram import SECRET

BOT_TOKEN = '12345:' + 'x' * 32
BINDINGS = {(1, 1): 'owner'}
PROFILE = {'operating_cpm': '1.25', 'target_all_mile_rpm': '2.50',
           'minimum_job_charge': '100', 'equipment': '26ft box truck',
           'operating_context': 'solo, no hazmat'}


def sign_init_data(token, fields):
    check = '\n'.join(f'{key}={fields[key]}' for key in sorted(fields))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, 'hash': digest})


def launch(user_id=1, age=0, token=BOT_TOKEN, **extra):
    fields = {'auth_date': str(int(time.time()) - age),
              'user': json.dumps({'id': user_id, 'first_name': 'T'},
                                 separators=(',', ':'))}
    fields.update(extra)
    return sign_init_data(token, fields)


def rid():
    return uuid.uuid4().hex


def attempts_used(store):
    if store._db.execute("SELECT name FROM sqlite_master WHERE name='pilot_budget'").fetchone() is None:
        return 0
    return store._db.execute('SELECT COALESCE(SUM(attempts),0) FROM pilot_budget').fetchone()[0]


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    path = tmp_path / 'miniapp.sqlite3'
    policy = MemoryPolicy(version='test-miniapp-v1', processing_notice='Invented offline records only')
    inbox = PilotInbox(path, dict(BINDINGS), policy, clock=clock)
    inbox._opening = OpeningSessions(dict(BINDINGS))
    yield inbox
    inbox.close()


@pytest.fixture
def client(store):
    app = create_opening_app(store, webhook_secret=SECRET, allowed_host='testserver',
                             conversation=OpeningConversation(store), send=lambda *_: True,
                             miniapp_bot_token=BOT_TOKEN)
    with TestClient(app) as tested:
        yield tested


def consent(store):
    conversation = OpeningConversation(store)
    conversation.handle(1, 1, '/start')
    nonce = store._conversation_states['owner']['nonce']
    conversation.handle(1, 1, f'/reply {nonce} session')
    return conversation


def api(client, path, init_data, **body):
    return client.post(f'/miniapp/api/{path}', json={'initData': init_data, **body})


def price_post(client, update, message):
    body = {'update_id': update,
            'message': {'message_id': message, 'from': {'id': 1, 'is_bot': False},
                        'chat': {'id': 1, 'type': 'private'}, 'text': '/price'}}
    return client.post('/telegram/webhook', json=body,
                       headers={'x-telegram-bot-api-secret-token': SECRET})


def bot_confirm_current(conversation):
    conversation.handle(1, 1, '/refresh')
    conversation.handle(1, 1, 'skip')
    flow = conversation.inbox._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")


def test_initdata_valid_and_reused_across_requests(store, client):
    consent(store)
    data = launch()
    first = api(client, 'state', data)
    second = api(client, 'state', data)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()['state']['stage'] == 'profile'
    assert attempts_used(store) == 0


def test_initdata_tampered_rejected(store, client):
    consent(store)
    data = launch()
    tampered = data.replace('first_name', 'first_namf')
    assert tampered != data
    response = api(client, 'state', tampered)
    assert response.status_code == 400
    assert 'signature' in response.json()['error']


def test_initdata_wrong_token_rejected(store, client):
    consent(store)
    response = api(client, 'state', launch(token='99999:' + 'y' * 32))
    assert response.status_code == 400


@pytest.mark.parametrize('age', [3 * 3600, 25 * 3600, -3600])
def test_initdata_expired_and_future_rejected(store, client, age):
    consent(store)
    response = api(client, 'state', launch(age=age))
    assert response.status_code == 400


def test_old_launch_rejected_after_session_rotation(store, client):
    consent(store)
    first = launch(age=30)
    assert api(client, 'state', first).status_code == 200
    assert api(client, 'state', first).status_code == 200
    conversation = OpeningConversation(store)
    conversation.handle(1, 1, '/start')
    nonce = store._conversation_states['owner']['nonce']
    conversation.handle(1, 1, f'/reply {nonce} session')
    rotated = api(client, 'state', first)
    assert rotated.status_code == 403
    assert 'reopen' in rotated.json()['error'].lower()
    fresh = launch(age=0)
    assert api(client, 'state', fresh).status_code == 200


def test_old_launch_rejected_after_expiry_rotation(tmp_path, clock):
    path = tmp_path / 'rotation.sqlite3'
    policy = MemoryPolicy(version='test-miniapp-v1', processing_notice='Invented offline records only',
                          session_seconds=60)
    inbox = PilotInbox(path, dict(BINDINGS), policy, clock=clock)
    inbox._opening = OpeningSessions(dict(BINDINGS))
    try:
        consent(inbox)
        app = create_opening_app(inbox, webhook_secret=SECRET, allowed_host='testserver',
                                 conversation=OpeningConversation(inbox), send=lambda *_: True,
                                 miniapp_bot_token=BOT_TOKEN)
        with TestClient(app) as tested:
            first = launch(age=30)
            assert api(tested, 'state', first).status_code == 200
            clock.advance(61)
            assert api(tested, 'state', first).status_code == 403
            consent(inbox)
            assert api(tested, 'state', first).status_code == 403
            assert api(tested, 'state', launch(age=0)).status_code == 200
    finally:
        inbox.close()


def test_initdata_malformed_rejected(store, client):
    consent(store)
    assert api(client, 'state', 'not-a-query-string').status_code == 400
    assert api(client, 'state', '').status_code == 400
    assert api(client, 'state', launch() + '&hash=' + '0' * 64).status_code == 400


def test_initdata_user_shape_rejected():
    now = int(time.time())
    base = {'auth_date': str(now)}
    bot = {'id': 7, 'first_name': 'B', 'is_bot': True}
    signed = sign_init_data(BOT_TOKEN, {**base, 'user': json.dumps(bot)})
    with pytest.raises(ValueError):
        verify_init_data(signed, BOT_TOKEN, now=now)
    bad = sign_init_data(BOT_TOKEN, {**base, 'user': json.dumps({'id': 'x'})})
    with pytest.raises(ValueError):
        verify_init_data(bad, BOT_TOKEN, now=now)
    missing = sign_init_data(BOT_TOKEN, base)
    with pytest.raises(ValueError):
        verify_init_data(missing, BOT_TOKEN, now=now)


def test_unknown_identity_rejected(store, client):
    consent(store)
    response = api(client, 'state', launch(user_id=999))
    assert response.status_code == 403


def test_ambiguous_binding_rejected(tmp_path, clock):
    path = tmp_path / 'ambiguous.sqlite3'
    policy = MemoryPolicy(version='test-miniapp-v1', processing_notice='Invented offline records only')
    inbox = PilotInbox(path, {(1, 1): 'a', (1, 2): 'b'}, policy, clock=clock)
    try:
        with pytest.raises(PermissionError):
            resolve_owner(inbox, 1)
    finally:
        inbox.close()


def test_consent_required(store, client):
    response = api(client, 'state', launch())
    assert response.status_code == 403


def test_expired_consent_rejected(tmp_path, clock):
    path = tmp_path / 'expired.sqlite3'
    policy = MemoryPolicy(version='test-miniapp-v1', processing_notice='Invented offline records only',
                          session_seconds=60)
    inbox = PilotInbox(path, dict(BINDINGS), policy, clock=clock)
    inbox._opening = OpeningSessions(dict(BINDINGS))
    try:
        consent(inbox)
        clock.advance(61)
        app = create_opening_app(inbox, webhook_secret=SECRET, allowed_host='testserver',
                                 conversation=OpeningConversation(inbox), send=lambda *_: True,
                                 miniapp_bot_token=BOT_TOKEN)
        with TestClient(app) as tested:
            response = api(tested, 'state', launch())
        assert response.status_code == 403
    finally:
        inbox.close()


def test_cross_session_isolation(tmp_path, clock):
    path = tmp_path / 'isolation.sqlite3'
    policy = MemoryPolicy(version='test-miniapp-v1', processing_notice='Invented offline records only')
    inbox = PilotInbox(path, {(1, 1): 'owner', (2, 2): 'other'}, policy, clock=clock)
    inbox._opening = OpeningSessions({(1, 1): 'owner', (2, 2): 'other'})
    try:
        conversation = OpeningConversation(inbox)
        conversation.handle(1, 1, '/start')
        nonce = inbox._conversation_states['owner']['nonce']
        conversation.handle(1, 1, f'/reply {nonce} session')
        app = create_opening_app(inbox, webhook_secret=SECRET, allowed_host='testserver',
                                 conversation=conversation, send=lambda *_: True,
                                 miniapp_bot_token=BOT_TOKEN)
        with TestClient(app) as tested:
            assert api(tested, 'state', launch(user_id=1)).status_code == 200
            assert api(tested, 'state', launch(user_id=2)).status_code == 403
    finally:
        inbox.close()


def test_host_mismatch_rejected(store):
    app = create_opening_app(store, webhook_secret=SECRET, allowed_host='miniapp.test',
                             conversation=OpeningConversation(store), send=lambda *_: True,
                             miniapp_bot_token=BOT_TOKEN)
    with TestClient(app) as tested:
        assert tested.get('/miniapp/').status_code == 404
        assert tested.get('/miniapp/app.js').status_code == 404
        response = api(tested, 'state', launch())
        assert response.status_code == 403


def test_page_served_with_protections(store, client):
    response = client.get('/miniapp/')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'https://telegram.org' in response.headers['Content-Security-Policy']
    assert 'X-Frame-Options' not in response.headers
    assert 'frame-ancestors' not in response.headers.get('Content-Security-Policy', '')
    assert 'axle' in response.text
    assert BOT_TOKEN not in response.text and SECRET not in response.text


def test_served_scripts_comply_with_served_csp(store, client):
    import re
    from pathlib import Path
    page = client.get('/miniapp/')
    csp = page.headers['Content-Security-Policy']
    assert "'unsafe-inline'" not in csp.split('script-src')[1].split(';')[0]
    scripts = re.findall(r'<script([^>]*)>(.*?)</script>', page.text, re.S)
    assert scripts, 'expected script tags'
    for attrs, code in scripts:
        assert code.strip() == '', 'inline script violates served CSP'
        match = re.search(r'src="([^"]+)"', attrs)
        assert match, 'script without src violates served CSP'
        src = match.group(1)
        assert src in ('https://telegram.org/js/telegram-web-app.js', '/miniapp/app.js'), src
    handlers = re.findall(r'\s(on(?:click|load|error|submit|change|input|focus|blur|key\w*))=', page.text)
    assert handlers == []
    asset = client.get('/miniapp/app.js')
    assert asset.status_code == 200
    assert asset.headers['Content-Type'].startswith('application/javascript')
    assert asset.headers['Cache-Control'] == 'no-store'
    assert asset.headers['X-Content-Type-Options'] == 'nosniff'
    shipped = Path('src/axle_hackathon/miniapp_app.js').read_text()
    assert asset.text == shipped and 'initData' in asset.text
    assert BOT_TOKEN not in asset.text and SECRET not in asset.text


def profiled(client, data=None, fields=None):
    data = data or launch()
    response = api(client, 'profile', data, request_id=rid(), fields=fields or dict(PROFILE))
    assert response.status_code == 200
    state = response.json()['state']
    assert state['staged_profile']['minimum_job_charge']['value'] == '100'
    assert state['stage_token']
    confirmed = api(client, 'profile/confirm', data, request_id=rid(),
                    stage_token=state['stage_token'])
    assert confirmed.status_code == 200
    assert confirmed.json()['state']['stage'] == 'photo'
    return data


def test_profile_submit_review_confirm(store, client):
    consent(store)
    profiled(client)
    profile = store._opening.get_profile(1, 1)
    assert str(profile.minimum_job_charge) == '100'
    assert store._conversation_states['owner']['step'] == 'photo'
    assert attempts_used(store) == 0


def test_profile_invalid_rejected_without_staging(store, client):
    consent(store)
    data = launch()
    bad = dict(PROFILE)
    del bad['minimum_job_charge']
    response = api(client, 'profile', data, request_id=rid(), fields=bad)
    assert response.status_code == 400
    assert 'Minimum charge' in response.json()['error']
    with pytest.raises(KeyError):
        store._opening.get_profile(1, 1)
    state = api(client, 'state', data, request_id=rid()).json()['state']
    assert state['stage'] == 'profile' and state['staged_profile'] is None


def test_profile_confirm_requires_exact_staged_token(store, client):
    consent(store)
    data = launch()
    first = api(client, 'profile', data, request_id=rid(), fields=dict(PROFILE))
    token_a = first.json()['state']['stage_token']
    missing = api(client, 'profile/confirm', data, request_id=rid())
    assert missing.status_code == 400
    wrong = api(client, 'profile/confirm', data, request_id=rid(), stage_token='0' * 22)
    assert wrong.status_code == 409 and wrong.json()['conflict'] is True
    second = api(client, 'profile', data, request_id=rid(), fields=dict(PROFILE))
    token_b = second.json()['state']['stage_token']
    assert token_b != token_a
    stale = api(client, 'profile/confirm', data, request_id=rid(), stage_token=token_a)
    assert stale.status_code == 409
    with pytest.raises(KeyError):
        store._opening.get_profile(1, 1)
    fresh = api(client, 'profile/confirm', data, request_id=rid(), stage_token=token_b)
    assert fresh.status_code == 200
    assert store._opening.profile_version(1, 1) == 1


def test_profile_confirm_rejected_after_bot_change(store, client):
    conversation = consent(store)
    data = launch()
    staged = api(client, 'profile', data, request_id=rid(), fields=dict(PROFILE))
    token = staged.json()['state']['stage_token']
    conversation.handle(1, 1, 'cpm 2.00; target 3.00; minimum 50')
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    assert store._opening.profile_version(1, 1) == 1
    stale = api(client, 'profile/confirm', data, request_id=rid(), stage_token=token)
    assert stale.status_code == 409
    assert stale.json()['state']['stage'] == 'photo'
    assert str(store._opening.get_profile(1, 1).operating_cpm) == '2.00'


def test_duplicate_profile_request_never_reexecutes(store, client):
    consent(store)
    data = launch()
    first = api(client, 'profile', data, request_id='a' * 32, fields=dict(PROFILE))
    assert first.status_code == 200
    again = api(client, 'profile', data, request_id='a' * 32, fields=dict(PROFILE))
    assert again.status_code == 200 and again.json()['duplicate'] is True
    rows = store._db.execute('SELECT count(*) FROM miniapp_requests').fetchone()[0]
    assert rows == 1


def shot(store, update=50):
    token = store._active['owner'].token
    h15.submit_shot(store, token, update=update, message=update)
    assert h15.worker(store, []).tick() == 'completed'


def reviewed(client, store, corrections=('reposition 20', 'availability feasible')):
    data = profiled(client)
    shot(store)
    pairs = {}
    for entry in corrections:
        name, _, value = entry.partition(' ')
        canonical = {'reposition': 'reposition_miles', 'availability': 'availability',
                     'deadhead': 'deadhead_miles'}.get(name, name)
        pairs[canonical] = value
    response = api(client, 'correct', data, request_id=rid(), expected_revision=1,
                   fields=pairs)
    assert response.status_code == 200
    return data


def test_correct_and_confirm_flow(store, client):
    consent(store)
    data = reviewed(client, store)
    state = api(client, 'state', data).json()['state']
    assert state['stage'] == 'review' and state['review']['revision'] == 2
    assert state['review']['pricing']['reposition_miles']['value'] == '20'
    assert state['review']['facts']['deadhead_miles']['source'] == 'screenshot'
    assert state['review']['pricing']['reposition_miles']['source'] == 'carrier'
    confirmed = api(client, 'confirm', data, request_id=rid(), revision=2)
    assert confirmed.status_code == 200
    assert confirmed.json()['state']['stage'] == 'confirmed'
    assert store._opening.get(1, 1).confirmed
    assert attempts_used(store) == 1


def test_stale_revision_conflicts_with_current_state(store, client):
    consent(store)
    data = reviewed(client, store)
    response = api(client, 'correct', data, request_id=rid(), expected_revision=1,
                   fields={'reposition_miles': '30'})
    assert response.status_code == 409
    body = response.json()
    assert body['conflict'] is True and body['state']['review']['revision'] == 2
    stale = api(client, 'confirm', data, request_id=rid(), revision=1)
    assert stale.status_code == 409
    assert not store._opening.get(1, 1).confirmed


def test_duplicate_correct_request_applies_once(store, client):
    consent(store)
    data = profiled(client)
    shot(store)
    first = api(client, 'correct', data, request_id='b' * 32, expected_revision=1,
                fields={'reposition_miles': '20'})
    assert first.status_code == 200
    again = api(client, 'correct', data, request_id='b' * 32, expected_revision=1,
                fields={'reposition_miles': '20'})
    assert again.status_code == 200 and again.json()['duplicate'] is True
    assert store._opening.get(1, 1).revision == 2


def test_bot_edit_invalidates_miniapp_review(store, client):
    conversation = consent(store)
    data = reviewed(client, store)
    conversation.handle(1, 1, 'target 2.10')
    assert store._opening.get(1, 1).revision == 3
    stale = api(client, 'confirm', data, request_id=rid(), revision=2)
    assert stale.status_code == 409
    assert stale.json()['state']['review']['revision'] == 3


def test_miniapp_edit_invalidates_bot_flow(store, client):
    conversation = consent(store)
    data = reviewed(client, store)
    conversation.handle(1, 1, '/refresh')
    conversation.handle(1, 1, 'skip')
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    assert store._conversation_states['owner']['step'] == 'confirmed'
    before = store._conversation_states['owner']['nonce']
    mine = api(client, 'correct', data, request_id=rid(), expected_revision=2,
               fields={'reposition_miles': '25'})
    assert mine.status_code == 200
    flow = store._conversation_states['owner']
    assert flow['nonce'] != before and flow['step'] == 'review' and flow['revision'] == 3
    with pytest.raises(ValueError, match='Stale'):
        conversation.handle(1, 1, f'/confirm {before}')
    token = store._active['owner'].token
    with pytest.raises(ValueError):
        store.submit(1, 1, 70, 'opening', token=token, revision=2, message_id=70)


def test_miniapp_confirm_keeps_bot_price_available(store, client):
    conversation = consent(store)
    data = reviewed(client, store)
    assert api(client, 'confirm', data, request_id=rid(), revision=2).status_code == 200
    flow = store._conversation_states['owner']
    assert flow['revision'] == 2
    refreshed = conversation.handle(1, 1, '/refresh')
    assert 'revision 2' in refreshed
    token = store._active['owner'].token
    assert store.submit(1, 1, 71, 'opening', token=token, revision=2, message_id=71) is True


def confirmed_review(client, store):
    data = reviewed(client, store)
    assert api(client, 'confirm', data, request_id=rid(), revision=2).status_code == 200
    return data


def tick_opening(store, sent=None):
    inner = h15.delegator(store, [], image_text=h15.draft_text())
    worker = OpeningWorker(store, inner, lambda c, t: (sent if sent is not None else []).append(t) or True,
                           global_limit=10, carrier_limit=10)
    assert worker.tick() == 'completed'


def evaluation_rows(store):
    return store._db.execute("SELECT update_id, status FROM pilot_updates WHERE action='opening'").fetchall()


def test_evaluate_queues_once_and_spends_once(store, client):
    consent(store)
    data = confirmed_review(client, store)
    first = api(client, 'evaluate', data, request_id='c' * 32, revision=2)
    assert first.status_code == 200
    assert first.json()['evaluation']['state'] == 'pending'
    assert first.json()['state']['stage'] == 'evaluating'
    again = api(client, 'evaluate', data, request_id='c' * 32, revision=2)
    assert again.status_code == 200 and again.json()['duplicate'] is True
    other = api(client, 'evaluate', data, request_id=rid(), revision=2)
    assert other.status_code == 200
    assert other.json()['evaluation'] == first.json()['evaluation']
    assert len(evaluation_rows(store)) == 1
    assert attempts_used(store) == 1
    sent = []
    tick_opening(store, sent)
    assert 'NEGOTIATE' in sent[0] and 'DRAFT — NOT SENT' in sent[0]
    decided = api(client, 'state', data).json()['state']
    assert decided['stage'] == 'decided'
    assert decided['evaluation_kind'] == 'offer_evaluation'
    assert decided['result']['decision'] == 'NEGOTIATE'
    assert 'DRAFT — NOT SENT' in decided['guidance']
    late = api(client, 'evaluate', data, request_id=rid(), revision=2)
    assert late.json()['evaluation']['state'] == 'completed'
    assert len(evaluation_rows(store)) == 1


def test_concurrent_evaluate_queues_once(store, client):
    consent(store)
    data = confirmed_review(client, store)

    def ask(suffix):
        return api(client, 'evaluate', data, request_id=suffix * 32, revision=2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(ask, ('d', 'e')))
    assert first.status_code == 200 and second.status_code == 200
    assert len(evaluation_rows(store)) == 1
    assert first.json()['evaluation']['update_id'] == second.json()['evaluation']['update_id']


def test_miniapp_then_bot_price_queues_once(store, client):
    conversation = consent(store)
    data = reviewed(client, store)
    bot_confirm_current(conversation)
    first = api(client, 'evaluate', data, request_id=rid(), revision=2)
    assert first.json()['evaluation']['state'] == 'pending'
    assert price_post(client, 90, 90).json() == {'status': 'duplicate'}
    assert len(evaluation_rows(store)) == 1
    tick_opening(store)
    assert attempts_used(store) == 2


def test_bot_price_then_miniapp_queues_once(store, client):
    conversation = consent(store)
    data = reviewed(client, store)
    bot_confirm_current(conversation)
    assert price_post(client, 90, 90).json() == {'status': 'queued'}
    again = api(client, 'evaluate', data, request_id=rid(), revision=2)
    assert again.json()['evaluation'] == {'state': 'pending', 'update_id': 90}
    assert len(evaluation_rows(store)) == 1
    tick_opening(store)
    assert attempts_used(store) == 2


def test_repeated_and_concurrent_bot_price_queues_once(store, client):
    conversation = consent(store)
    data = reviewed(client, store)
    bot_confirm_current(conversation)
    assert price_post(client, 90, 90).json() == {'status': 'queued'}
    assert price_post(client, 91, 91).json() == {'status': 'duplicate'}
    assert len(evaluation_rows(store)) == 1
    tick_opening(store)
    conversation.handle(1, 1, 'target 2.60')
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    # Concurrent race at the shared submit path (webhook ordering would
    # legitimately stale one of two racing bot messages instead).
    token = store._active['owner'].token

    def ask(n):
        return store.submit(1, 1, 100 + n, 'opening', token=token, revision=3)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(ask, (0, 1))) == [False, True]
    assert len(evaluation_rows(store)) == 2
    tick_opening(store)
    assert attempts_used(store) == 3


def test_concurrent_bot_and_miniapp_queue_once(store, client):
    conversation = consent(store)
    data = reviewed(client, store)
    bot_confirm_current(conversation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        bot = pool.submit(price_post, client, 90, 90)
        app = pool.submit(api, client, 'evaluate', data, request_id=rid(), revision=2)
        bot_status = bot.result(timeout=10).json()['status']
        app_body = app.result(timeout=10).json()
    assert bot_status in ('queued', 'duplicate')
    assert app_body['evaluation']['state'] == 'pending'
    rows = evaluation_rows(store)
    assert len(rows) == 1
    assert (bot_status == 'queued') == (rows[0][0] == 90)
    tick_opening(store)
    assert attempts_used(store) == 2


def test_new_confirmed_revision_permits_evaluation(store, client):
    consent(store)
    data = confirmed_review(client, store)
    assert api(client, 'evaluate', data, request_id=rid(), revision=2).status_code == 200
    tick_opening(store)
    correct = api(client, 'correct', data, request_id=rid(), expected_revision=2,
                  fields={'counter': '650'})
    assert correct.json()['state']['review']['revision'] == 3
    assert api(client, 'confirm', data, request_id=rid(), revision=3).status_code == 200
    assert api(client, 'evaluate', data, request_id=rid(), revision=3).status_code == 200
    assert len(evaluation_rows(store)) == 2
    tick_opening(store)
    assert attempts_used(store) == 3
    final = api(client, 'state', data).json()['state']
    assert final['result']['decision'] == 'ACCEPT'


def test_evaluate_requires_confirmed_current_revision(store, client):
    consent(store)
    data = reviewed(client, store)
    unconfirmed = api(client, 'evaluate', data, request_id=rid(), revision=2)
    assert unconfirmed.status_code == 409
    assert evaluation_rows(store) == []
    stale = api(client, 'evaluate', data, request_id=rid(), revision=1)
    assert stale.status_code == 409
    assert evaluation_rows(store) == []


def test_unknown_and_explicit_zero_through_miniapp(store, client):
    consent(store)
    data = profiled(client)
    shot(store)
    response = api(client, 'correct', data, request_id=rid(), expected_revision=1,
                   fields={'deadhead_miles': 'unknown', 'reposition_miles': '0',
                           'availability': 'feasible'})
    assert response.status_code == 200
    review = response.json()['state']['review']
    assert review['facts']['deadhead_miles']['state'] == 'unknown'
    assert review['pricing']['reposition_miles']['state'] == 'explicit_zero'
    assert api(client, 'confirm', data, request_id=rid(), revision=2).status_code == 200
    assert api(client, 'evaluate', data, request_id=rid(), revision=2).status_code == 200
    tick_opening(store)
    decided = api(client, 'state', data).json()['state']
    assert decided['result']['decision'] == 'NEED_MORE_INFORMATION'
    assert 'deadhead_miles' in decided['result']['missing_information']


def test_forget_via_miniapp(store, client):
    consent(store)
    data = reviewed(client, store)
    forgotten = api(client, 'forget', data, request_id=rid())
    assert forgotten.status_code == 200 and forgotten.json()['forgotten'] is True
    assert api(client, 'state', launch()).status_code == 403
    with pytest.raises(KeyError):
        store._opening.get(1, 1)
    assert 'owner' not in store._conversation_states


def test_button_sender_payload_and_bounds():
    seen = {}

    def handle(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(
            {'ok': True, 'result': {'message_id': 1, 'chat': {'id': 1, 'type': 'private'}}}
        ).encode()))
    with httpx.Client(transport=httpx.MockTransport(handle)) as raw:
        button = TelegramWebAppButton(raw, BOT_TOKEN, allowed_chats={1},
                                      allowed_host='miniapp.test', seconds=1)
        assert button.web_app_url == 'https://miniapp.test/miniapp/'
        assert button(1, 'invented', label='Open Axle review') is True
        assert seen['reply_markup'] == {'inline_keyboard': [
            [{'text': 'Open Axle review',
              'web_app': {'url': 'https://miniapp.test/miniapp/'}}]]}
        with pytest.raises(PermissionError):
            button(2, 'invented', label='Open Axle review')
        with pytest.raises(ValueError):
            button(1, 'invented', label='')
        with pytest.raises(ValueError):
            button(1, 'invented', label='x' * 65)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, stream=httpx.ByteStream(b'{"ok":false}')))) as raw:
        with pytest.raises(RuntimeError):
            TelegramWebAppButton(raw, BOT_TOKEN, allowed_chats={1},
                                 allowed_host='miniapp.test', seconds=1)(1, 'invented', label='x')


def test_app_command_sends_button(store):
    calls = []
    app = create_opening_app(store, webhook_secret=SECRET, allowed_host='testserver',
                             conversation=OpeningConversation(store), send=lambda *_: True,
                             miniapp_bot_token=BOT_TOKEN,
                             miniapp_button=lambda c, t, *, label: calls.append((c, t, label)) or True)
    consent(store)
    body = {'update_id': 90, 'message': {'message_id': 90, 'from': {'id': 1, 'is_bot': False},
                                         'chat': {'id': 1, 'type': 'private'}, 'text': '/app'}}
    headers = {'x-telegram-bot-api-secret-token': SECRET}
    with TestClient(app) as tested:
        assert tested.post('/telegram/webhook', json=body, headers=headers).json() == {'status': 'processed'}
        assert tested.post('/telegram/webhook', json=body, headers=headers).json() == {'status': 'duplicate'}
    assert len(calls) == 1 and calls[0][0] == 1 and calls[0][2] == 'Open Axle review'


def test_app_command_requires_consent(store):
    app = create_opening_app(store, webhook_secret=SECRET, allowed_host='testserver',
                             conversation=OpeningConversation(store), send=lambda *_: True,
                             miniapp_bot_token=BOT_TOKEN,
                             miniapp_button=lambda c, t, *, label: True)
    body = {'update_id': 91, 'message': {'message_id': 91, 'from': {'id': 1, 'is_bot': False},
                                         'chat': {'id': 1, 'type': 'private'}, 'text': '/app'}}
    headers = {'x-telegram-bot-api-secret-token': SECRET}
    with TestClient(app) as tested:
        assert tested.post('/telegram/webhook', json=body, headers=headers).status_code == 403


def test_full_miniapp_journey_with_simulated_counteroffer(store, client):
    conversation = consent(store)
    data = launch()
    assert api(client, 'state', data).json()['state']['stage'] == 'profile'
    profiled(client, data)
    assert api(client, 'state', data).json()['state']['stage'] == 'photo'
    shot(store)
    trip = api(client, 'correct', data, request_id=rid(), expected_revision=1,
               fields={'deadhead_miles': '40', 'reposition_miles': '20',
                       'duration_note': '6 hours', 'availability': 'feasible',
                       'handling_note': 'liftgate required'})
    assert trip.json()['state']['review']['revision'] == 2
    assert api(client, 'confirm', data, request_id=rid(), revision=2).status_code == 200
    queued = api(client, 'evaluate', data, request_id=rid(), revision=2)
    assert queued.json()['evaluation']['state'] == 'pending'
    sent = []
    tick_opening(store, sent)
    first = api(client, 'state', data).json()['state']
    assert first['stage'] == 'decided' and first['result']['decision'] == 'NEGOTIATE'
    counter = api(client, 'correct', data, request_id=rid(), expected_revision=2,
                  fields={'counter': '650'})
    assert counter.json()['state']['review']['revision'] == 3
    assert counter.json()['state']['review']['counter_offer']['value'] == '650'
    assert api(client, 'confirm', data, request_id=rid(), revision=3).status_code == 200
    assert api(client, 'evaluate', data, request_id=rid(), revision=3).status_code == 200
    tick_opening(store, sent)
    final = api(client, 'state', data).json()['state']
    assert final['stage'] == 'decided' and final['result']['decision'] == 'ACCEPT'
    assert 'DRAFT — NOT SENT' in final['result']['notice']
    assert 'not a booking' in final['guidance']
    assert attempts_used(store) == 3
    raw = json.dumps(final)
    assert SECRET not in raw and BOT_TOKEN not in raw
    assert store._active['owner'].token not in raw
    flow = store._conversation_states['owner']
    assert flow['revision'] == 3
