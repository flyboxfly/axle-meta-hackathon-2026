"""Local client contract tests. No live Muse or paid model calls."""
import pytest
from fastapi.testclient import TestClient
from axle_hackathon.app import app
from test_h1 import BASE, COMPLETE


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AXLE_DEMO_TOKEN', 'offline-h7')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    return TestClient(app, headers={'Authorization': 'Bearer offline-h7'})


def payload(target='2.00', opportunity=None):
    return {'opportunity': COMPLETE if opportunity is None else opportunity,
            'benchmark': {'target_all_mile_rpm': target, 'confirmed': True},
            'facts_confirmed': True, 'source': 'screenshot'}


def test_external_client_target_sequence_without_model(client):
    results = [client.post('/api/v1/axle/evaluate', json=payload(t)) for t in ['2.00','1.75',None]]
    assert all(r.status_code == 200 and r.headers['cache-control'] == 'no-store' for r in results)
    bodies = [r.json() for r in results]
    values = [b['evaluation'] for b in bodies]
    assert [v['decision'] for v in values] == ['NEGOTIATE','ACCEPT','NEED_MORE_INFORMATION']
    assert [v['revenue_gap_to_target'] for v in values] == ['60.00','0.00',None]
    assert all(v['estimated_operating_cost'] == '290.00' and v['estimated_operating_surplus_after_allocated_costs'] == '130.00' for v in values)
    assert all(b['model_invoked'] is False and b['confirmation_basis'] == 'caller_assertion' for b in bodies)
    assert bodies[-1]['next_questions'][0]['field'] == 'carrier_revenue_target'
    assert bodies[0]['next_questions'] == []


@pytest.mark.parametrize('change', [
    {'benchmark':None}, {'benchmark':{'confirmed':True}},
    {'benchmark':{'target_all_mile_rpm':'2','confirmed':False}},
    {'benchmark':{'target_all_mile_rpm':'2','confirmed':'true'}},
    {'facts_confirmed':False}, {'facts_confirmed':1},
    {'carrier_id':'other'}, {'source':'model_verified'},
    {'benchmark':{'target_all_mile_rpm':'2.001','confirmed':True}},
])
def test_invalid_assertions_fail_closed(client, change):
    assert client.post('/api/v1/axle/evaluate', json=payload() | change).status_code == 422


def test_no_implicit_benchmark_or_confirmation(client):
    for key in ['benchmark','facts_confirmed','source']:
        body=payload(); del body[key]
        assert client.post('/api/v1/axle/evaluate', json=body).status_code == 422


def test_unknown_costs_questions_and_profile_restriction(client):
    r=client.post('/api/v1/axle/evaluate', json=payload(opportunity=BASE)).json()
    assert r['evaluation']['estimated_operating_cost'] is None
    assert r['next_questions'][0]['field'] == 'diesel_per_gallon'
    op=COMPLETE | {'equipment':'power_only_amazon_provided_trailer'}
    r=client.post('/api/v1/axle/evaluate', json=payload(opportunity=op)).json()
    assert r['evaluation']['decision'] == 'NEED_MORE_INFORMATION'
    assert r['next_questions'][0]['field'] == 'matching_equipment_carrier_profile'


def test_local_boundary_and_authentication(client, monkeypatch):
    assert client.post('/api/v1/axle/evaluate', json=payload(), headers={'Authorization':'Bearer wrong'}).status_code == 401
    assert client.post('/api/v1/axle/evaluate', json=payload(), headers={'Host':'example.com'}).status_code == 403
    assert client.post('/api/v1/axle/evaluate', json=payload(), headers={'Origin':'https://example.com'}).status_code == 403
    monkeypatch.delenv('AXLE_DEMO_TOKEN')
    assert client.post('/api/v1/axle/evaluate', json=payload()).status_code == 503


def test_openapi_and_legacy_default_preserved(client):
    schema=client.get('/openapi.json').json()
    assert schema['paths']['/api/v1/axle/evaluate']['post']['operationId'] == 'evaluate_confirmed_freight_opportunity'
    r=client.post('/api/v1/freight/evaluate', json=COMPLETE).json()
    assert r['benchmark_source'] == 'synthetic_default'
    assert r['target_all_mile_rpm'] == '2.00'
