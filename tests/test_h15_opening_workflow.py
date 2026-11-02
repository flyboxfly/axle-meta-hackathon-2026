"""Offline opening-workflow integration tests. Invented figures only, no live calls."""
import io
import json
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import axle_hackathon.pilot_factory as factory
import axle_hackathon.pilot_launch as launch
from axle_hackathon.opening_meta import OpeningDelegator
from axle_hackathon.opening_telegram import OpeningConversation, create_opening_app
from axle_hackathon.opening_workflow import OpeningSessions
from axle_hackathon.pilot_inbox import PilotInbox
from axle_hackathon.pilot_memory import MemoryPolicy
from axle_hackathon.pilot_runtime import OpeningWorker
from test_h13_memory import Clock
from test_h13_telegram import SECRET
from test_h13_transports import TOKEN, response

BINDINGS = {(1, 1): 'owner'}


@pytest.fixture
def store(tmp_path):
    path = tmp_path / 'opening.sqlite3'
    policy = MemoryPolicy(version='test-opening-v1', processing_notice='Invented offline records only')
    inbox = PilotInbox(path, dict(BINDINGS), policy, clock=Clock())
    inbox._opening = OpeningSessions(dict(BINDINGS))
    yield inbox
    inbox.close()


def session(store, choice='session_only'):
    notice = store.disclosure(1, 1)
    return store.consent(1, 1, notice.token, choice)


def png_bytes(size=(20, 20)):
    buffer = io.BytesIO()
    Image.new('RGB', size, 'blue').save(buffer, format='PNG')
    return buffer.getvalue()


def jpeg_bytes(size=(20, 20)):
    # Telegram photo sizes are JPEG files; documents carry their own MIME type.
    buffer = io.BytesIO()
    Image.new('RGB', size, 'blue').save(buffer, format='JPEG')
    return buffer.getvalue()


def draft_text(**facts):
    values = dict(payout=None, loaded_miles=None, deadhead_miles=None, weight_lbs=None)
    evidence = {name: '' for name in values}
    for name, item in facts.items():
        values[name], evidence[name] = item
    return json.dumps(dict(status='UNCONFIRMED', facts=values, evidence=evidence, issues=[]))


def extraction_response(text):
    return NS(status='completed', output_text=text, id='resp-invented-1',
              usage={'input_tokens': 10, 'output_tokens': 5}, output=[])


def selection_response(revision):
    call = NS(type='function_call', status='completed', name='review_confirmed_opening',
              arguments=json.dumps({'revision': revision}))
    return NS(status='completed', output=[call], id='resp-invented-2', usage=None)


def delegator(store, calls, image_text=None, fail=None):
    raw = png_bytes()
    media = NS(fetch=lambda file_id, mime: (raw, mime))
    def image_create(**payload):
        calls.append(('image', payload['model']))
        if fail == 'model':
            raise RuntimeError('invented provider failure')
        return extraction_response(image_text)
    def text_create(**payload):
        calls.append(('text', payload['model'], payload.get('parallel_tool_calls')))
        if fail == 'model':
            raise RuntimeError('invented provider failure')
        assert 'revision' in json.loads(payload['input'])
        return selection_response(json.loads(payload['input'])['revision'])
    image = NS(responses=NS(create=image_create))
    text = NS(responses=NS(create=text_create))
    return OpeningDelegator(store, store._opening, image, text, media=media)


def worker(store, calls, **limits):
    inner = delegator(store, calls, image_text=draft_text(
        payout=('420', 'Total payout $420'), loaded_miles=('180', 'Loaded 180 mi'),
        deadhead_miles=('40', 'Deadhead 40 mi')))
    return OpeningWorker(store, inner, lambda *_: True,
                         global_limit=limits.get('global_limit', 4),
                         carrier_limit=limits.get('carrier_limit', 4))


def submit_shot(store, token, update=50, message=50):
    return store.submit(1, 1, update, 'screenshot', token=token, message_id=message,
        media=dict(file_id='file-1', file_unique_id='unique-1', mime='image/png',
                   reported_size=100))


def ready_revision(store):
    conversation = OpeningConversation(store)
    conversation.handle(1, 1, '/start')
    nonce = store._conversation_states['owner']['nonce']
    conversation.handle(1, 1, f'/reply {nonce} session')
    access = NS(token=store._active['owner'].token)
    calls = []
    submit_shot(store, access.token)
    assert worker(store, calls).tick() == 'completed'
    return access, conversation, calls


def test_screenshot_creates_unconfirmed_draft_revision(store):
    access, _, calls = ready_revision(store)
    snapshot = store._opening.get(1, 1)
    assert snapshot.revision == 1 and not snapshot.confirmed
    assert str(snapshot.draft.facts.payout) == '420'
    assert calls == [('image', 'muse-wonder-1.0')]
    assert store._db.execute('SELECT SUM(attempts) FROM pilot_budget').fetchone() == (1,)


def test_duplicate_photo_delivers_single_extraction(store):
    access = session(store)
    calls = []
    worker(store, calls)
    assert submit_shot(store, access.token)
    assert not submit_shot(store, access.token)
    assert worker(store, calls).tick() == 'completed'
    assert worker(store, calls).tick() == 'idle'
    assert calls == [('image', 'muse-wonder-1.0')]


def test_correction_invalidates_confirmation_and_stale_price_rejected(store):
    access, conversation, _ = ready_revision(store)
    flow = store._conversation_states['owner']
    conversation.handle(1, 1, f"/confirm {flow['nonce']}")
    assert store._opening.get(1, 1).confirmed
    conversation.handle(1, 1, 'target 2.50')
    snapshot = store._opening.get(1, 1)
    assert snapshot.revision == 2 and not snapshot.confirmed
    with pytest.raises(ValueError):
        store.submit(1, 1, 60, 'opening', token=access.token, revision=1, message_id=60)
    with pytest.raises(ValueError):
        store._opening.confirm(1, 1, 1)


def test_inflight_correction_blocks_old_pricing_result(store):
    access, conversation, _ = ready_revision(store)
    store._opening.confirm(1, 1, 1)
    store.submit(1, 1, 61, 'opening', token=access.token, revision=1, message_id=61)
    sent, entered, release = [], Event(), Event()
    inner = delegator(store, [], image_text=draft_text())
    real = inner.select_pricing
    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return real(*args, **kwargs)
    inner.select_pricing = slow
    worker = OpeningWorker(store, inner, lambda c, t: sent.append(t) or True,
                           global_limit=4, carrier_limit=4)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(worker.tick)
        try:
            assert entered.wait(5)
            conversation.handle(1, 1, 'target 2.10')
        finally:
            release.set()
        assert task.result(timeout=5) == 'uncertain'
    assert sent == []
    assert store._db.execute("SELECT status FROM pilot_updates WHERE update_id=61").fetchone() == ('uncertain',)


def test_consent_withdrawn_inflight_blocks_delivery(store):
    access, _, _ = ready_revision(store)
    store._opening.confirm(1, 1, 1)
    store.submit(1, 1, 62, 'opening', token=access.token, revision=1, message_id=62)
    sent, entered, release = [], Event(), Event()
    inner = delegator(store, [], image_text=draft_text())
    real = inner.select_pricing
    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return real(*args, **kwargs)
    inner.select_pricing = slow
    worker = OpeningWorker(store, inner, lambda c, t: sent.append(t) or True,
                           global_limit=4, carrier_limit=4)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(worker.tick)
        try:
            assert entered.wait(5)
            store.forget(1, 1)
        finally:
            release.set()
        assert task.result(timeout=5) == 'uncertain'
    assert sent == []


def test_budget_counts_every_model_attempt(store):
    access = session(store)
    calls = []
    worker(store, calls, carrier_limit=1)
    submit_shot(store, access.token)
    assert worker(store, calls, carrier_limit=1).tick() == 'completed'
    submit_shot(store, access.token, update=51, message=51)
    assert worker(store, calls, carrier_limit=1).tick() == 'uncertain'
    assert len(calls) == 1
    assert store._db.execute('SELECT attempts FROM pilot_budget').fetchone() == (1,)


def test_crash_recovery_marks_screenshot_uncertain_without_replay(store):
    access = session(store)
    submit_shot(store, access.token)
    claim, _ = store.claim_screenshot(1, 1, 50, access.token)
    path = store._db.execute('PRAGMA database_list').fetchone()[2]
    store.close()
    reopened = PilotInbox(path, dict(BINDINGS),
        MemoryPolicy(version='test-opening-v1', processing_notice='Invented offline records only'))
    reopened._opening = OpeningSessions(dict(BINDINGS))
    try:
        assert reopened._db.execute('SELECT status FROM pilot_updates').fetchone() == ('uncertain',)
        fresh = session(reopened)
        assert not reopened.submit(1, 1, 50, 'screenshot', token=fresh.token, message_id=50,
            media=dict(file_id='file-1', file_unique_id='unique-1', mime='image/png'))
    finally:
        reopened.close()


@pytest.mark.parametrize('failure', ['media', 'model', 'delivery'])
def test_failures_are_uncertain_without_retry(store, failure):
    access = session(store)
    calls = []
    raw = png_bytes()
    if failure == 'media':
        media = NS(fetch=lambda *args: (_ for _ in ()).throw(ValueError('Reported file size exceeds limit')))
    else:
        media = NS(fetch=lambda file_id, mime: (raw, mime))
    inner = delegator(store, calls, image_text=draft_text(), fail='model' if failure == 'model' else None)
    inner._media = media
    sends = []
    def send(chat, text):
        sends.append(text)
        if failure == 'delivery':
            raise RuntimeError('invented sender failure')
        return True
    worker = OpeningWorker(store, inner, send, global_limit=4, carrier_limit=4)
    submit_shot(store, access.token)
    assert worker.tick() == 'uncertain'
    assert worker.tick() == 'idle'
    assert len(calls) <= 1 and len(sends) <= 1


def test_itemized_costs_require_normalization(store):
    _, conversation, _ = ready_revision(store)
    with pytest.raises(ValueError, match='normalization'):
        conversation.handle(1, 1, 'cpm itemized')
    assert store._opening.get(1, 1).revision == 1
    store._opening.confirm(1, 1, 1)
    with pytest.raises(ValueError, match='normalization'):
        store._opening.price(1, 1, 1)


def test_unknown_mileage_and_explicit_zero_minimum(store):
    _, conversation, _ = ready_revision(store)
    conversation.handle(1, 1, 'loaded unknown')
    conversation.handle(1, 1, 'minimum none')
    conversation.handle(1, 1, 'cpm 1.25')
    snapshot = store._opening.get(1, 1)
    assert snapshot.draft.facts.loaded_miles is None
    assert str(snapshot.pricing.minimum_job_charge) == '0'
    store._opening.confirm(1, 1, snapshot.revision)
    with pytest.raises(ValueError, match='loaded miles'):
        store._opening.price(1, 1, snapshot.revision)


def test_format_mismatch_fails_closed_without_model_call(store):
    # Regression: bytes that do not match the declared photo/document type
    # are rejected after download and never reach the model.
    access = session(store)
    calls = []
    inner = delegator(store, calls, image_text=draft_text())
    inner._media = NS(fetch=lambda file_id, mime: (png_bytes(), 'image/jpeg'))
    worker = OpeningWorker(store, inner, lambda *_: True, global_limit=4, carrier_limit=4)
    store.submit(1, 1, 50, 'screenshot', token=access.token, message_id=50,
        media=dict(file_id='file-1', file_unique_id='unique-1', mime='image/jpeg'))
    assert worker.tick() == 'uncertain'
    assert worker.tick() == 'idle'
    assert calls == []
    assert store._db.execute('SELECT SUM(attempts) FROM pilot_budget').fetchone() == (1,)


def test_no_screenshot_bytes_in_durable_storage(store):
    ready_revision(store)
    found = []
    tables = [row[0] for row in store._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for table in tables:
        for row in store._db.execute(f'SELECT * FROM "{table}"').fetchall():
            found.append(repr(row))
    dump = '\n'.join(found)
    assert 'Total payout' not in dump and 'x89PNG' not in dump
    media = store._db.execute('SELECT file_id,mime FROM pilot_media').fetchone()
    assert media == ('file-1', 'image/png')


def test_price_reply_is_internal_draft_without_reservation(store):
    access, conversation, _ = ready_revision(store)
    for correction in ('target 2.50', 'cpm 1.25', 'minimum 100', 'reposition 0'):
        conversation.handle(1, 1, correction)
    snapshot = store._opening.get(1, 1)
    store._opening.confirm(1, 1, snapshot.revision)
    store.submit(1, 1, 63, 'opening', token=access.token, revision=snapshot.revision, message_id=63)
    sent = []
    inner = delegator(store, [], image_text=draft_text())
    worker = OpeningWorker(store, inner, lambda c, t: sent.append(t) or True,
                           global_limit=4, carrier_limit=4)
    assert worker.tick() == 'completed'
    assert 'DRAFT — NOT SENT' in sent[0] and 'reservation' not in sent[0].lower()
    assert 'Opening bid: $550.00' in sent[0]
    assert access.token not in sent[0]


def test_selection_payload_carries_no_identity_or_token(store):
    access, conversation, _ = ready_revision(store)
    for correction in ('target 2.50', 'cpm 1.25', 'minimum 100', 'reposition 0'):
        conversation.handle(1, 1, correction)
    revision = store._opening.get(1, 1).revision
    store._opening.confirm(1, 1, revision)
    seen = {}
    inner = delegator(store, [], image_text=draft_text())
    real_create = inner._text.responses.create
    def capture(**payload):
        seen.update(payload=json.dumps(payload))
        return real_create(**payload)
    inner._text.responses.create = capture
    worker = OpeningWorker(store, inner, lambda *_: True, global_limit=4, carrier_limit=4)
    store.submit(1, 1, 64, 'opening', token=access.token, revision=revision, message_id=64)
    assert worker.tick() == 'completed'
    assert access.token not in seen['payload']
    assert '"user"' not in seen['payload'] and '"chat"' not in seen['payload']


def test_new_screenshot_carries_pricing_unconfirmed(store):
    access, conversation, _ = ready_revision(store)
    conversation.handle(1, 1, 'target 2.50')
    store._opening.confirm(1, 1, 2)
    submit_shot(store, access.token, update=55, message=55)
    calls = []
    assert worker(store, calls).tick() == 'completed'
    snapshot = store._opening.get(1, 1)
    assert snapshot.revision == 3 and not snapshot.confirmed
    assert str(snapshot.pricing.target_all_mile_rpm) == '2.50'
    with pytest.raises(ValueError):
        store.submit(1, 1, 66, 'opening', token=access.token, revision=3, message_id=66)


def test_expired_consent_blocks_queued_screenshot(tmp_path):
    clock = Clock()
    policy = MemoryPolicy(version='test-opening-v1', processing_notice='Invented offline records only',
                          session_seconds=60)
    inbox = PilotInbox(tmp_path / 'expiry.sqlite3', dict(BINDINGS), policy, clock=clock)
    inbox._opening = OpeningSessions(dict(BINDINGS))
    try:
        access = session(inbox)
        submit_shot(inbox, access.token)
        clock.advance(61)
        calls = []
        assert worker(inbox, calls).tick() == 'uncertain'
        assert calls == []
    finally:
        inbox.close()


def test_full_opening_host_rehearsal(tmp_path, monkeypatch):
    raw = jpeg_bytes()
    models, sent, clients = [], [], []
    delivered, priced = Event(), Event()
    def handle(request):
        if request.url.host == 'api.meta.ai':
            payload = json.loads(request.content)
            assert payload.get('model') == 'muse-wonder-1.0'
            models.append('tools' in payload)
            if 'tools' in payload:
                revision = json.loads(payload['input'])['revision']
                return response(200, json_value={'status': 'completed', 'output': [{
                    'type': 'function_call', 'status': 'completed',
                    'name': 'review_confirmed_opening',
                    'arguments': json.dumps({'revision': revision})}],
                    'id': 'resp-selection', 'usage': None})
            return response(200, json_value={'status': 'completed', 'output': [],
                'output_text': draft_text(payout=('420', 'Total payout $420'),
                    loaded_miles=('180', 'Loaded 180 mi'), deadhead_miles=('40', 'Deadhead 40 mi')),
                'id': 'resp-extraction', 'usage': {'input_tokens': 10, 'output_tokens': 5}})
        path = request.url.path
        if path.endswith('/getFile'):
            file_id = json.loads(request.content)['file_id']
            return response(200, json_value={'ok': True, 'result': {
                'file_id': file_id, 'file_path': 'photos/f1.jpg', 'file_size': len(raw)}})
        if '/file/' in path:
            return response(200, content=raw)
        text = json.loads(request.content)['text']
        sent.append(text)
        if 'UNCONFIRMED screenshot draft' in text:
            delivered.set()
        if 'Preliminary opening price' in text:
            priced.set()
        return response(200, json_value={'ok': True, 'result': {
            'message_id': len(sent), 'chat': {'id': 1, 'type': 'private'}}})
    real_client = factory.create_http_client
    def client(**kwargs):
        created = real_client(**kwargs)
        clients.append(created)
        return created
    monkeypatch.setattr(httpx, 'HTTPTransport', lambda **kwargs: httpx.MockTransport(handle))
    monkeypatch.setattr(factory, 'create_http_client', client)
    host = factory.build_opening_host(tmp_path / 'host.sqlite3', dict(BINDINGS),
        MemoryPolicy(version='real-opening-v1', processing_notice='Invented offline rehearsal'),
        provider_key='invented-key', bot_token=TOKEN, webhook_secret=SECRET,
        allowed_host='testserver', global_limit=4, carrier_limit=4)
    try:
        with TestClient(host) as client:
            headers = {'X-Telegram-Bot-Api-Secret-Token': SECRET}
            def post(payload, update_id):
                response = client.post('/telegram/webhook', json=payload, headers=headers)
                assert response.status_code == 200
                return response.json()['status']
            def command(text, update_id):
                return post(dict(update_id=update_id, message=dict(
                    message_id=update_id, **{'from': dict(id=1, is_bot=False)},
                    chat=dict(id=1, type='private'), text=text)), update_id)
            def nonce():
                return sent[-1].split('\nStep: ')[1].split('\n')[0]
            assert command('/start', 1) == 'processed'
            assert command(f'/reply {nonce()} session', 2) == 'processed'
            photo = [dict(file_id='file-1', file_unique_id='unique-1', file_size=len(raw))]
            assert post(dict(update_id=3, message=dict(message_id=3,
                **{'from': dict(id=1, is_bot=False)},
                chat=dict(id=1, type='private'), photo=photo)), 3) == 'queued'
            assert post(dict(update_id=3, message=dict(message_id=3,
                **{'from': dict(id=1, is_bot=False)},
                chat=dict(id=1, type='private'), photo=photo)), 3) == 'duplicate'
            assert delivered.wait(10)
            assert command('target 2.50', 4) == 'processed'
            assert command('cpm 1.25', 5) == 'processed'
            assert command('minimum 100', 6) == 'processed'
            assert command('reposition 20', 7) == 'processed'
            assert command(f"/confirm {nonce()}", 8) == 'processed'
            assert command('/price', 9) == 'queued'
            assert priced.wait(10)
            assert command('/price', 9) == 'duplicate'
            assert any('Opening bid: $600.00' in text for text in sent)
            assert all('synthetic' not in text.lower() for text in sent)
            assert all('invented-key' not in text and TOKEN not in text for text in sent)
            assert command('/forget', 10) == 'queued'
            assert not host.owner.inbox._active
            total = host.owner.inbox._db.execute('SELECT SUM(attempts) FROM pilot_budget').fetchone()[0]
            assert total == 2
        assert models == [False, True]
    finally:
        host.owner.close(timeout=5)
    assert all(host.last_shutdown.values())
    assert all(c.is_closed for c in clients)


def test_media_before_consent_rejected_without_fetch(tmp_path, monkeypatch):
    from axle_hackathon.pilot_transports import TelegramMedia
    store = None
    path = tmp_path / 'guard.sqlite3'
    policy = MemoryPolicy(version='test-opening-v1', processing_notice='Invented offline records only')
    store = PilotInbox(path, dict(BINDINGS), policy)
    store._opening = OpeningSessions(dict(BINDINGS))
    try:
        fetched = []
        media = TelegramMedia(httpx.Client(transport=httpx.MockTransport(
            lambda request: fetched.append(1) or response(200, json_value={'ok': True,
                'result': {'file_id': 'x', 'file_path': 'photos/x.jpg'}}))), TOKEN, seconds=1)
        inner = OpeningDelegator(store, store._opening, NS(), NS(), media=media)
        with pytest.raises(PermissionError):
            inner.extract(1, 1, 'bogus-token', 'x', 'image/png', expected_revision=0)
        assert fetched == []
        app = create_opening_app(store, webhook_secret=SECRET, allowed_host='testserver',
                                 conversation=OpeningConversation(store), send=lambda *_: True)
        with TestClient(app) as client:
            photo = [dict(file_id='x', file_unique_id='u', file_size=10)]
            response = client.post('/telegram/webhook', json=dict(update_id=1, message=dict(
                message_id=1, **{'from': dict(id=1, is_bot=False)},
                chat=dict(id=1, type='private'), photo=photo)),
                headers={'X-Telegram-Bot-Api-Secret-Token': SECRET})
            assert response.status_code == 403
        assert fetched == []
    finally:
        store.close()


def test_opening_host_cleanup_on_client_failure(tmp_path, monkeypatch):
    clients = []
    def client(**kwargs):
        if clients:
            raise RuntimeError('invented-private-detail')
        created = httpx.Client(transport=httpx.MockTransport(lambda request: None))
        clients.append(created)
        return created
    monkeypatch.setattr(factory, 'create_http_client', client)
    with pytest.raises(RuntimeError, match='^Opening host construction failed; cleanup attempted$'):
        factory.build_opening_host(tmp_path / 'fail.sqlite3', dict(BINDINGS),
            MemoryPolicy(version='test', processing_notice='Invented offline records only'),
            provider_key='invented-key', bot_token=TOKEN, webhook_secret=SECRET,
            allowed_host='testserver', global_limit=4, carrier_limit=4)
    assert clients[0].is_closed


def real_config(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / 'private.json'
    path.write_text(json.dumps(dict(approved_real_opening_test=True, provider_key='invented',
        bot_token=TOKEN, webhook_secret=SECRET, allowed_host='testserver', user_id=1, chat_id=1)))
    path.chmod(0o600)
    return path


def test_real_config_accepts_distinct_key_and_rejects_synthetic(tmp_path):
    from test_h13_launch import config as synthetic_config
    (tmp_path / 'real').mkdir()
    (tmp_path / 'synthetic').mkdir()
    real = real_config(tmp_path / 'real')
    data, db = launch.read_real_config(real)
    assert data['user_id'] == 1 and db == real.parent / 'pilot.sqlite3'
    synthetic = synthetic_config(tmp_path / 'synthetic')
    with pytest.raises(RuntimeError, match='^Private pilot configuration rejected$'):
        launch.read_real_config(synthetic)
    with pytest.raises(RuntimeError, match='^Private pilot configuration rejected$'):
        launch.read_private_config(real)


def test_prepare_opening_cli_writes_real_config(tmp_path, monkeypatch, capsys):
    import axle_hackathon.pilot_setup as setup
    from test_h13_setup import identity, info, operator, update
    tmp_path.chmod(0o700)
    path = tmp_path / 'private.json'
    answers = iter(['PREPARE NEW OPENING TEST', TOKEN, 'invented', 'invented-provider-key',
                    'invented.trycloudflare.com', '1', '1', 'invented enrollment phrase'])
    monkeypatch.setattr(setup.getpass, 'getpass', lambda prompt: next(answers))
    monkeypatch.setattr(setup.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(setup.sys.stderr, 'isatty', lambda: True)
    monkeypatch.setattr(setup.sys, 'argv', ['pilot_setup', 'prepare-opening'])
    monkeypatch.setenv('AXLE_PILOT_CONFIG_FILE', str(path))
    monkeypatch.setattr(setup, 'configure_private_logging', lambda: None)
    monkeypatch.setattr(setup.os, 'umask', lambda mode: None)
    bot, _ = operator([identity(), info(), [update()], info(), []])
    monkeypatch.setattr(setup, 'create_http_client', lambda **kwargs: bot.client)
    assert setup.main() == 0
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
    assert launch.read_real_config(path)[0]['approved_real_opening_test'] is True
