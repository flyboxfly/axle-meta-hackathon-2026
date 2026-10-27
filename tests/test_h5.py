"""Offline browser completion and CLI failure boundaries; no live reliability claim."""
import json
from types import SimpleNamespace as NS

import httpx
import pytest
from openai import APITimeoutError

from axle_hackathon import web
from axle_hackathon.economics import evaluate
from axle_hackathon.meta_agent import delegate
from test_h1 import COMPLETE
from test_h2 import browser


def tool_call(**updates):
    return NS(**dict(dict(type='function_call', status='completed',
        name='evaluate_freight_opportunity', arguments=json.dumps(COMPLETE),
        call_id='offline-tool'), **updates))


def response_with(*calls, status='completed'):
    return NS(id='offline-selection', status=status, output=list(calls))


def install_client(monkeypatch, respond):
    requests = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['timeout'] == 20
            assert kwargs['max_retries'] == 0
            self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            requests.append(kwargs)
            return respond(len(requests), kwargs)
    monkeypatch.setenv('MODEL_API_KEY', 'PRIVATE_KEY')
    monkeypatch.setattr('openai.OpenAI', Client)
    return requests


def payload(target='1.75', **updates):
    return dict(dict(message='PRIVATE_CARRIER_MESSAGE', opportunity=COMPLETE,
        source='screenshot', screenshot_confirmed=True,
        benchmark={'target_all_mile_rpm': target, 'confirmed': True}), **updates)


def test_browser_timeout_fails_closed(browser, monkeypatch, caplog):
    def timeout(*args):
        raise APITimeoutError(request=httpx.Request('POST',
            'https://api.meta.ai/v1/responses',
            headers={'Authorization': 'PRIVATE_TOKEN'}, content=b'PRIVATE_BODY'))
    calls = install_client(monkeypatch, timeout)
    response = browser.post('/api/v1/browser/evaluate', json=payload())
    assert response.status_code == 502
    assert 'evaluation' not in response.json()
    assert len(calls) == 1
    assert 'stage=tool_selection turn=1 validated_evaluations=0 elapsed_ms=' in caplog.text
    assert 'category=provider_timeout' in caplog.text
    assert 'PRIVATE_' not in caplog.text + response.text
    assert not web._gate.locked()


def test_cli_still_requires_followup_and_propagates_timeout(caplog):
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        if len(requests) == 1:
            return response_with(tool_call())
        raise APITimeoutError(request=httpx.Request('POST',
            'https://api.meta.ai/v1/responses', content=b'PRIVATE_BODY'))
    with pytest.raises(APITimeoutError):
        delegate(NS(responses=NS(create=create)), 'PRIVATE_MESSAGE', evaluate)
    assert len(requests) == 2
    assert requests[1]['input'][0]['type'] == 'function_call_output'
    assert 'stage=after_tool turn=2 validated_evaluations=1 elapsed_ms=' in caplog.text
    assert 'PRIVATE_' not in caplog.text


@pytest.mark.parametrize('target,decision,gap', [
    ('2.00', 'NEGOTIATE', '60.00'), ('1.75', 'ACCEPT', '0.00'),
    (None, 'NEED_MORE_INFORMATION', None)])
def test_browser_single_request_canonical_completion(browser, monkeypatch, target, decision, gap):
    def respond(count, kwargs):
        assert count == 1, 'Browser must not request model follow-up'
        assert kwargs['max_output_tokens'] == 2000
        assert 'previous_response_id' not in kwargs
        facts = json.loads(kwargs['input'].split('\n')[-1])
        assert 'target_all_mile_rpm' not in facts
        return response_with(tool_call(arguments=json.dumps(facts)),
            NS(type='message', content='PRIVATE_MODEL_PROSE'))
    calls = install_client(monkeypatch, respond)
    result = browser.post('/api/v1/browser/evaluate', json=payload(target))
    assert result.status_code == 200
    body = result.json()
    assert len(calls) == 1
    assert body['evaluation']['decision'] == decision
    assert body['evaluation']['revenue_gap_to_target'] == gap
    assert body['evaluation']['estimated_operating_cost'] == '290.00'
    assert body['evaluation']['estimated_operating_surplus_after_allocated_costs'] == '130.00'
    assert body['trace'][0]['status'] == 'executed_and_validated'
    assert body['trace'][0]['model_received_result'] is False
    assert body['trace'][0]['result_delivery'] == 'canonical_ui'
    assert body['response_id'] == body['trace'][0]['response_id'] == 'offline-selection'
    assert 'PRIVATE_' not in result.text
    assert 'answer' not in body


@pytest.mark.parametrize('selection', [
    response_with(),
    response_with(tool_call(), tool_call(call_id='second')),
    response_with(tool_call(name='PRIVATE_UNKNOWN_TOOL')),
    response_with(tool_call(arguments='PRIVATE_INVALID_JSON')),
    response_with(tool_call(arguments=json.dumps(dict(COMPLETE, payout='999')))),
    response_with(tool_call(arguments=json.dumps(dict(COMPLETE, target_all_mile_rpm='0.01')))),
    response_with(tool_call(status='in_progress')),
    response_with(tool_call(), status='incomplete'),
    response_with(tool_call(), status='failed'),
    response_with(tool_call(), status='cancelled'),
])
def test_unverified_selection_never_returns_decision(browser, monkeypatch, caplog, selection):
    calls = install_client(monkeypatch, lambda *args: selection)
    result = browser.post('/api/v1/browser/evaluate', json=payload())
    assert result.status_code == 502
    assert 'evaluation' not in result.json()
    assert len(calls) == 1
    assert 'PRIVATE_' not in result.text + caplog.text
    assert not web._gate.locked()


def test_multiple_calls_rejected_before_any_execution(browser, monkeypatch):
    install_client(monkeypatch, lambda *args: response_with(tool_call(), tool_call()))
    monkeypatch.setattr(web, 'evaluate', lambda *args, **kwargs: pytest.fail('Executed ambiguous calls'))
    assert browser.post('/api/v1/browser/evaluate', json=payload()).status_code == 502


@pytest.mark.parametrize('kind', ['exception', 'invalid_output'])
def test_calculation_failure_cannot_become_browser_success(browser, monkeypatch, caplog, kind):
    calls = install_client(monkeypatch, lambda *args: response_with(tool_call()))
    def fail(*args, **kwargs):
        if kind == 'exception': raise RuntimeError('PRIVATE_CALCULATION_FAILURE')
        return {'decision': 'ACCEPT'}
    monkeypatch.setattr(web, 'evaluate', fail)
    result = browser.post('/api/v1/browser/evaluate', json=payload())
    assert result.status_code == 502
    assert 'evaluation' not in result.json()
    assert len(calls) == 1
    assert 'PRIVATE_' not in caplog.text + result.text
    assert not web._gate.locked()


def test_unconfirmed_screenshot_blocks_model_request(browser, monkeypatch):
    calls = install_client(monkeypatch, lambda *args: pytest.fail('Unconfirmed facts reached model'))
    result = browser.post('/api/v1/browser/evaluate', json=payload(screenshot_confirmed=False))
    assert result.status_code == 422
    assert not calls


def test_installed_sdk_browser_completion_uses_one_request(browser, monkeypatch):
    from openai import OpenAI
    captured = []
    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        assert len(captured) == 1
        facts = json.loads(body['input'].split('\n')[-1])
        return httpx.Response(200, json={
            'id': 'offline-sdk-selection', 'object': 'response', 'created_at': 0,
            'model': 'muse-spark-1.3', 'status': 'completed',
            'output': [{'type': 'function_call', 'id': 'offline-fc', 'status': 'completed',
                        'name': 'evaluate_freight_opportunity', 'arguments': json.dumps(facts),
                        'call_id': 'offline-sdk-call'}]})
    def factory(**kwargs):
        return OpenAI(**kwargs, http_client=httpx.Client(
            transport=httpx.MockTransport(handler), trust_env=False))
    monkeypatch.setenv('MODEL_API_KEY', 'offline-placeholder')
    monkeypatch.setattr('openai.OpenAI', factory)
    result = browser.post('/api/v1/browser/evaluate', json=payload())
    assert result.status_code == 200
    assert result.json()['evaluation']['decision'] == 'ACCEPT'
    assert len(captured) == 1
    assert captured[0]['model'] == 'muse-spark-1.3'
    assert captured[0]['tools'][0]['name'] == 'evaluate_freight_opportunity'
    assert 'tool_choice' not in captured[0]  # Model selects; not forced or fabricated.
