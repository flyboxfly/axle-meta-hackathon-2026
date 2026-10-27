"""Offline boundary tests; fake model responses are not live Meta proof."""
import json
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from axle_hackathon.app import app
from axle_hackathon import web
from test_h1 import BASE, COMPLETE

@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setenv('AXLE_DEMO_TOKEN', 'offline-test')
    web._attempts.clear()
    client = TestClient(app, base_url='http://127.0.0.1:8000')
    client.auth = ('carrier', 'offline-test')
    return client

def fake_client(monkeypatch, mutate=False):
    class Client:
        def __init__(self, **kw):
            self.responses=self
            self.count=0
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def create(self, **kw):
            self.count+=1
            if self.count==1:
                facts=json.loads(kw['input'].split('\n')[-1])
                if mutate: facts['payout']='999'
                return NS(id='offline-call',status='completed',output=[NS(type='function_call',status='completed',name='evaluate_freight_opportunity',arguments=json.dumps(facts),call_id='offline-tool')])
            return NS(id='offline-final',output=[],output_text='Ignored model prose',usage=None)
    monkeypatch.setenv('MODEL_API_KEY','offline-placeholder')
    monkeypatch.setattr('openai.OpenAI',Client)

def test_browser_boundary(browser):
    assert browser.get('/').status_code==200
    assert browser.get('/',auth=('carrier','wrong')).status_code==401
    assert browser.get('/',headers={'Host':'attacker.test'}).status_code==403
    assert browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE},headers={'Origin':'https://attacker.test'}).status_code==403
    assert browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE,'message':'x'*1501}).status_code==422

def test_transition_and_canonical_output(browser,monkeypatch):
    fake_client(monkeypatch)
    results=[]
    for op in [BASE,COMPLETE,dict(COMPLETE,payout='500')]:
        response=browser.post('/api/v1/browser/evaluate',json={'opportunity':op})
        assert response.status_code==200
        results.append(response.json()['evaluation'])
        assert 'answer' not in response.json()
    assert [r['decision'] for r in results]==['NEED_MORE_INFORMATION','NEGOTIATE','ACCEPT']
    assert results[0]['estimated_operating_cost'] is None
    assert results[1]['estimated_operating_surplus_after_allocated_costs']=='130.00'

def test_changed_model_inputs_fail_closed(browser,monkeypatch):
    fake_client(monkeypatch,mutate=True)
    response=browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE})
    assert response.status_code==502
    assert 'evaluation' not in response.json()

def test_missing_key_rate_and_concurrency(browser,monkeypatch):
    monkeypatch.delenv('MODEL_API_KEY',raising=False)
    assert browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE}).status_code==503
    web._gate.acquire()
    try:
        assert browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE}).status_code==429
    finally: web._gate.release()
    fake_client(monkeypatch)
    for _ in range(3): assert browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE}).status_code==200
    assert browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE}).status_code==429

def test_model_error_is_sanitized(browser,monkeypatch):
    def fail(body): raise RuntimeError('sensitive provider detail')
    monkeypatch.setattr(web,'live_run',fail)
    response=browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE})
    assert response.status_code==502
    assert 'sensitive' not in response.text

@pytest.mark.parametrize('kind,category', [(ValueError,'delegation_validation'),(RuntimeError,'delegation_protocol'),(Exception,'unexpected_error')])
def test_diagnostics_exclude_exception_text(browser,monkeypatch,caplog,kind,category):
    def fail(body): raise kind('secret-provider-body-and-token')
    monkeypatch.setattr(web,'live_run',fail)
    response=browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE})
    assert response.status_code==502
    assert category in caplog.text
    assert 'secret-provider-body-and-token' not in caplog.text + response.text


def test_non_ascii_incorrect_password_is_unauthorized(browser):
    import base64
    authorization = "Basic " + base64.b64encode("carrier:wrongé".encode("utf-8")).decode("ascii")
    response = browser.get("/", headers={"Authorization": authorization}, auth=None)
    assert response.status_code == 401
    assert "Basic" in response.headers["www-authenticate"]
