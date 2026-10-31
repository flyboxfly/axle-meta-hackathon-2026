"""Mock-only adapter tests; no network calls."""
import json
from types import SimpleNamespace as NS

import pytest

from axle_hackathon.pilot_meta import PilotDelegator
from test_h13_memory import setup, consent
from test_h13_pilot import profile, offer


def response(arguments='{"revision":1}', **changes):
    values = dict(status='completed', output=[NS(type='function_call', status='completed',
        name='review_confirmed_planning', arguments=arguments)])
    values.update(changes)
    return NS(**values)


def adapter(store, run):
    return PilotDelegator(store, NS(responses=NS(create=run)))


def ready(store, origin='synthetic'):
    access = consent(store)
    store.put(1, 1, access.token, profile(), offer(origin=origin), expected_revision=0)
    store.confirm(1, 1, access.token, 1)
    return access


def test_selected_tool_returns_canonical_result_and_minimal_scope(setup):
    store, _, _, _ = setup
    access = ready(store)
    calls = []
    def run(**kwargs):
        calls.append(kwargs)
        payload = json.loads(kwargs['input'])
        assert set(payload) == {'revision', 'opportunity'}
        assert access.token not in kwargs['input']
        assert 'target_all_mile_rpm' not in kwargs['input']
        return response()
    result = adapter(store, run).evaluate(1, 1, access.token, 1)
    assert len(calls) == 1
    assert result['evaluation']['gap'] == '60.00'
    assert result['trace']['model_received_result'] is False


@pytest.mark.parametrize('raw', ['{}', '{"revision":2}', '{"revision":true}',
    '{"revision":1.0}', '{"revision":1,"carrier":"b"}',
    '{"revision":1,"revision":1}', '[]', 'bad json'])
def test_invalid_model_arguments_fail_closed(setup, raw):
    store, _, _, _ = setup
    access = ready(store)
    with pytest.raises(ValueError, match='Invalid model delegation'):
        adapter(store, lambda **kw: response(raw)).evaluate(1, 1, access.token, 1)


@pytest.mark.parametrize('action', ['edit', 'forget', 'expire', 'renew'])
def test_inflight_results_rejected_after_state_changes(setup, action):
    store, _, clock, _ = setup
    access = ready(store)
    def run(**kwargs):
        if action == 'edit':
            store.put(1, 1, access.token, profile(), offer(origin='synthetic', payout='800'), expected_revision=1)
        elif action == 'forget':
            store.forget(1, 1)
        elif action == 'expire':
            clock.advance(60)
        else:
            ready(store)
        return response()
    with pytest.raises((PermissionError, ValueError)):
        adapter(store, run).evaluate(1, 1, access.token, 1)


def test_auth_and_real_data_guard_before_provider(setup):
    store, _, _, _ = setup
    access = ready(store, origin='real_offer')
    def forbidden(**kw):
        pytest.fail('Provider must not run')
    d = adapter(store, forbidden)
    with pytest.raises(PermissionError):
        d.evaluate(2, 2, access.token, 1)
    with pytest.raises(ValueError, match='Synthetic'):
        d.evaluate(1, 1, access.token, 1)


def test_provider_failure_is_sanitized_and_not_retried(setup):
    store, _, _, _ = setup
    access = ready(store)
    calls = []
    def run(**kw):
        calls.append(kw)
        raise RuntimeError('private provider body')
    with pytest.raises(RuntimeError, match='^Model selection failed; no automatic retry$'):
        adapter(store, run).evaluate(1, 1, access.token, 1)
    assert len(calls) == 1


@pytest.mark.parametrize('changes', [dict(status='incomplete'), dict(output=[]),
    dict(output=[NS(type='function_call',status='completed',name='wrong',arguments='{}')])])
def test_invalid_provider_completion(setup, changes):
    store, _, _, _ = setup
    access = ready(store)
    with pytest.raises(ValueError):
        adapter(store, lambda **kw: response(**changes)).evaluate(1, 1, access.token, 1)
