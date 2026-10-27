"""Offline image/protocol/boundary tests; not live vision accuracy evidence."""
import base64
from io import BytesIO
import json
from types import SimpleNamespace as NS
from PIL import Image, PngImagePlugin
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from axle_hackathon import web, vision
from axle_hackathon.schemas import Opportunity
from test_h1 import BASE
from test_h2 import browser


def png(size=(40, 30), note=None):
    output = BytesIO()
    info = PngImagePlugin.PngInfo()
    if note: info.add_text('Comment', note)
    Image.new('RGB', size, 'white').save(output, format='PNG', pnginfo=info)
    return output.getvalue()


def send(browser, data=None, **headers):
    return browser.post('/api/v1/browser/screenshot', content=png() if data is None else data,
                        headers={'Content-Type': 'image/png', 'X-Axle-Synthetic': 'true', **headers})


def fake_vision(monkeypatch, output=None):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['max_retries'] == 0
            assert kwargs['timeout'] == 20
            self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            calls.append(kwargs)
            return NS(id='offline-vision', status='completed', incomplete_details=None, output_text=json.dumps(output or {
                'facts': {'equipment': 'box_truck_26ft', 'payout': '420', 'loaded_miles': '180', 'deadhead_miles': None},
                'evidence': {'equipment': '26-foot box truck', 'payout': 'Total payout $420', 'loaded_miles': 'Loaded miles 180'},
                'issues': ['Confirm all additional miles from your actual position.']}))
    monkeypatch.setenv('MODEL_API_KEY', 'offline-placeholder')
    monkeypatch.setattr('openai.OpenAI', Client)
    return calls


def test_extraction_protocol_and_nulls(browser, monkeypatch):
    calls = fake_vision(monkeypatch)
    response = send(browser, png(note='private metadata'))
    assert response.status_code == 200
    data = response.json()
    assert data['requires_confirmation'] is True
    assert data['extraction']['facts']['deadhead_miles'] is None
    assert 'decision' not in data and 'evaluation' not in data
    assert len(calls) == 1 and 'tools' not in calls[0]
    assert calls[0]['text']['format']['type'] == 'json_schema'
    assert calls[0]['text']['format']['strict'] is True
    assert calls[0]['reasoning'] == {'effort': 'low'}
    assert calls[0]['max_output_tokens'] == 4096
    user = calls[0]['input'][0]
    assert user['role'] == 'user'
    content = user['content']
    assert content[0]['type'] == 'input_text'
    assert content[1]['type'] == 'input_image'
    encoded = content[1]['image_url'].split(',', 1)[1]
    with Image.open(BytesIO(base64.b64decode(encoded))) as image:
        assert 'Comment' not in image.info
    assert 'offline-placeholder' not in response.text


@pytest.mark.parametrize('data,media,status', [
    (b'', 'image/png', 413),
    (b'not an image', 'image/png', 415),
    (b'<svg/>', 'image/svg+xml', 415),
    (png(), 'image/jpeg', 415),
    (b'x' * (vision.MAX_IMAGE_BYTES + 1), 'image/png', 413),
    (png((4097, 1)), 'image/png', 413),
    (png((3000, 3000)), 'image/png', 413),
])
def test_invalid_images_never_reach_model(browser, monkeypatch, data, media, status):
    def fail(**kw): pytest.fail('Invalid image reached provider')
    monkeypatch.setattr('openai.OpenAI', fail)
    assert send(browser, data, **{'Content-Type': media}).status_code == status


def test_jpeg_metadata_removed():
    output = BytesIO()
    image = Image.new('RGB', (40, 30), 'white')
    exif = Image.Exif()
    exif[270] = 'private metadata'
    image.save(output, format='JPEG', exif=exif)
    normalized, media = vision.normalize_image(output.getvalue(), 'image/jpeg')
    assert media == 'image/jpeg'
    with Image.open(BytesIO(normalized)) as clean:
        assert not clean.getexif()


def test_animated_png_rejected():
    output = BytesIO()
    first = Image.new('RGB', (10, 10), 'white')
    first.save(output, format='PNG', save_all=True, append_images=[Image.new('RGB', (10, 10), 'black')], duration=50)
    with pytest.raises(HTTPException) as error:
        vision.normalize_image(output.getvalue(), 'image/png')
    assert error.value.status_code == 415


def test_auth_origin_and_synthetic_consent(browser):
    assert browser.post('/api/v1/browser/screenshot', content=png(), auth=None).status_code == 401
    assert send(browser, **{'Origin': 'https://attacker.test'}).status_code == 403
    assert send(browser, **{'X-Axle-Synthetic': 'false'}).status_code == 422


def test_screenshot_uses_shared_budget(browser, monkeypatch):
    fake_vision(monkeypatch)
    web._gate.acquire()
    try:
        assert send(browser).status_code == 429
    finally:
        web._gate.release()
    assert send(browser).status_code == 200
    for _ in range(3):
        assert browser.post('/api/v1/browser/evaluate', json={'opportunity': BASE}).status_code == 502
    assert send(browser).status_code == 429


def test_screenshot_confirmation_required(browser, monkeypatch):
    def forbidden(body): pytest.fail('Unconfirmed screenshot reached inference')
    monkeypatch.setattr(web, 'live_run', forbidden)
    assert browser.post('/api/v1/browser/evaluate', json={'opportunity': BASE, 'source': 'screenshot'}).status_code == 422
    assert browser.post('/api/v1/browser/evaluate', json={'opportunity': BASE, 'source': 'unknown'}).status_code == 422
    from axle_hackathon.economics import evaluate
    monkeypatch.setattr(web, 'live_run', lambda body: {'evaluation': evaluate(body.opportunity).model_dump()})
    result = browser.post('/api/v1/browser/evaluate', json={'opportunity': BASE, 'source': 'screenshot', 'screenshot_confirmed': True})
    assert result.status_code == 200
    assert result.json()['evaluation']['decision'] == 'NEED_MORE_INFORMATION'


def test_missing_supporting_text_does_not_fill_fact():
    result = vision.Extraction.validated_text(json.dumps({'facts': {'payout': '420'}, 'evidence': {}, 'issues': []}))
    assert result.facts.payout is None


@pytest.mark.parametrize('output', [
    {'facts': {'payout': 'NaN'}},
    {'facts': {'payout': '-1'}},
    {'facts': {'carrier_id': 'other'}},
    {'facts': {}, 'evidence': {'carrier_id': 'private'}},
    {'facts': {}, 'issues': ['x' * 241]},
])
def test_bad_extraction_fails_closed(browser, monkeypatch, output):
    fake_vision(monkeypatch, output)
    response = send(browser)
    assert response.status_code == 502
    assert 'extraction' not in response.json()


def test_provider_failure_is_sanitized(browser, monkeypatch, caplog):
    monkeypatch.setenv('MODEL_API_KEY', 'offline-placeholder')
    def fail(**kwargs): raise RuntimeError('PRIVATE_PROVIDER_DATA')
    monkeypatch.setattr('openai.OpenAI', fail)
    result = send(browser)
    assert result.status_code == 502
    assert 'PRIVATE_PROVIDER_DATA' not in caplog.text + result.text


def test_unknown_payout_does_not_become_zero(browser, monkeypatch):
    fake_vision(monkeypatch, {'facts': {'payout': None, 'loaded_miles': None}, 'issues': ['Base and bid are not a confirmed total.']})
    result = send(browser).json()
    assert result['extraction']['facts']['payout'] is None
    assert result['extraction']['facts']['loaded_miles'] is None


def test_local_blob_preview_allowed_by_csp(browser):
    policy = browser.get('/').headers['content-security-policy']
    assert "img-src 'self' blob:" in policy
    assert "connect-src 'self'" in policy


def test_schema_diagnostic_excludes_unknown_names_and_values(caplog):
    with pytest.raises(ValidationError):
        vision.Extraction.validated_text('{"facts":{"PRIVATE_UNKNOWN_FIELD":"PRIVATE_VALUE"}}')
    assert 'extra_forbidden' in caplog.text
    assert '[unknown]' in caplog.text
    assert 'PRIVATE_UNKNOWN_FIELD' not in caplog.text
    assert 'PRIVATE_VALUE' not in caplog.text


def test_strict_schema_is_closed_and_all_fields_required():
    def check(node):
        if isinstance(node, dict):
            if node.get('type') == 'object':
                assert node['additionalProperties'] is False
                assert set(node['required']) == set(node['properties'])
            for value in node.values(): check(value)
        elif isinstance(node, list):
            for value in node: check(value)
    check(vision.extraction_schema())


@pytest.mark.parametrize('status,text,reason', [
    ('incomplete', '', 'max_output_tokens'),
    ('completed', '', None),
    ('completed', '```json PRIVATE_RESPONSE_TEXT', None),
])
def test_incomplete_or_non_json_output_fails_without_raw_logging(caplog, status, text, reason):
    response = NS(status=status, output_text=text, incomplete_details=NS(reason=reason))
    with pytest.raises((RuntimeError, ValidationError)):
        vision.parse_extraction_response(response)
    assert 'Screenshot completion diagnostic:' in caplog.text
    assert 'PRIVATE_RESPONSE_TEXT' not in caplog.text
    if reason: assert reason in caplog.text


def test_installed_sdk_serializes_image_and_structured_format(monkeypatch):
    import httpx
    from openai import OpenAI
    captured = []
    draft = {'facts': {'equipment': 'box_truck_26ft', 'payout': 420, 'loaded_miles': 180, 'deadhead_miles': 60},
             'evidence': {'equipment': '26-foot box truck', 'payout': '$420', 'loaded_miles': '180', 'deadhead_miles': '60'},
             'issues': []}
    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(200, json={
            'id': 'offline-sdk-response', 'object': 'response', 'created_at': 0,
            'model': 'muse-spark-1.3', 'status': 'completed',
            'output': [{'type': 'message', 'id': 'offline-message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': json.dumps(draft), 'annotations': []}]}],
        })
    def factory(**kwargs):
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False))
    monkeypatch.setenv('MODEL_API_KEY', 'offline-placeholder')
    monkeypatch.setattr('openai.OpenAI', factory)
    result = vision.extract_screenshot(png(), 'image/png')
    assert result['response_id'] == 'offline-sdk-response'
    assert result['extraction']['facts']['payout'] == '420'
    assert captured[0]['text']['format']['strict'] is True
    assert captured[0]['reasoning']['effort'] == 'low'
    assert captured[0]['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,')
