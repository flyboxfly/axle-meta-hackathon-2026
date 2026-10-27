"""Offline failure injection, not evidence of live provider reliability."""
import httpx
import pytest
from openai import APITimeoutError, APIConnectionError, APIStatusError
from axle_hackathon import web
from axle_hackathon.schemas import Opportunity
from test_h1 import BASE
from test_h2 import browser, fake_client

@pytest.mark.parametrize('category', ['provider_timeout','provider_connection','provider_status','tool_schema_validation'])
def test_failure_category_redaction_and_recovery(browser, monkeypatch, caplog, category):
    request = httpx.Request('POST','https://api.meta.ai/v1/responses')
    def fail(body):
        if category == 'provider_timeout':
            raise APITimeoutError(request=request)
        if category == 'provider_connection':
            raise APIConnectionError(message='PRIVATE_PROVIDER_TEXT',request=request)
        if category == 'provider_status':
            response=httpx.Response(429,request=request)
            raise APIStatusError('PRIVATE_PROVIDER_TEXT',response=response,body={'private':'PRIVATE_PROVIDER_TEXT'})
        Opportunity(**dict(BASE,loaded_miles='PRIVATE_PROVIDER_TEXT'))
    original = web.live_run
    monkeypatch.setattr(web,'live_run',fail)
    response=browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE})
    assert response.status_code==502
    assert category in caplog.text
    assert 'PRIVATE_PROVIDER_TEXT' not in caplog.text + response.text
    if category=='provider_status': assert 'status=429' in caplog.text
    # Failure releases concurrency lock so the next deliberate request can run.
    monkeypatch.setattr(web,'live_run',original)
    fake_client(monkeypatch)
    assert browser.post('/api/v1/browser/evaluate',json={'opportunity':BASE}).status_code==200
