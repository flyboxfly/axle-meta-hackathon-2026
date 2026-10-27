"""Offline failure localization; does not establish live provider reliability."""
import json
from types import SimpleNamespace as NS

import httpx
import pytest
from openai import APITimeoutError

from axle_hackathon import web
from test_h1 import COMPLETE
from test_h2 import browser


@pytest.mark.parametrize('failed_turn,stage,validated', [
    (1, 'tool_selection', 0), (2, 'after_tool', 1)])
def test_timeout_stage_preserves_failure_boundary(browser, monkeypatch, caplog,
                                                failed_turn, stage, validated):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['timeout'] == 20
            assert kwargs['max_retries'] == 0
            self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == failed_turn:
                raise APITimeoutError(request=httpx.Request(
                    'POST', 'https://api.meta.ai/v1/responses',
                    headers={'Authorization': 'PRIVATE_TOKEN'},
                    content=b'PRIVATE_PROVIDER_BODY'))
            facts = json.loads(kwargs['input'].split('\n')[-1])
            return NS(id='PRIVATE_RESPONSE_ID', output=[NS(type='function_call',
                name='evaluate_freight_opportunity', arguments=json.dumps(facts),
                call_id='PRIVATE_CALL_ID')])
    monkeypatch.setenv('MODEL_API_KEY', 'PRIVATE_KEY')
    monkeypatch.setattr('openai.OpenAI', Client)
    response = browser.post('/api/v1/browser/evaluate', json={
        'message': 'PRIVATE_CARRIER_MESSAGE', 'opportunity': COMPLETE,
        'source': 'screenshot', 'screenshot_confirmed': True,
        'benchmark': {'target_all_mile_rpm': '1.75', 'confirmed': True}})
    assert response.status_code == 502
    assert 'evaluation' not in response.json()
    assert len(calls) == failed_turn  # No automatic retry or fallback.
    assert f'stage={stage} turn={failed_turn} validated_evaluations={validated}' in caplog.text
    assert 'elapsed_ms=' in caplog.text
    assert 'category=provider_timeout' in caplog.text
    assert 'PRIVATE_' not in caplog.text + response.text
    assert not web._gate.locked()
