import httpx
import pytest
from axle_hackathon.pilot_http import create_http_client


def test_client_sets_phase_limits_and_does_not_retry_or_redirect(monkeypatch):
    options=[];calls=[]
    def transport(**kwargs):
        options.append(kwargs)
        def handle(request):
            calls.append(request)
            return httpx.Response(302,headers={'location':'https://example.invalid/other'})
        return httpx.MockTransport(handle)
    monkeypatch.setattr(httpx,'HTTPTransport',transport)
    with create_http_client(connect=1,read=2,write=3,pool=4,connections=2) as client:
        assert client.get('https://example.invalid').status_code==302
        assert len(calls)==1
        assert calls[0].extensions['timeout']=={'connect':1,'read':2,'write':3,'pool':4}
        assert options[0]['retries']==0 and options[0]['trust_env'] is False
        assert options[0]['limits'].max_connections==2


def test_client_propagates_timeout_after_one_attempt(monkeypatch):
    calls=[]
    def transport(**kwargs):
        def handle(request):calls.append(1);raise httpx.ReadTimeout('invented timeout')
        return httpx.MockTransport(handle)
    monkeypatch.setattr(httpx,'HTTPTransport',transport)
    with create_http_client(connect=1,read=1,write=1,pool=1,connections=1) as client:
        with pytest.raises(httpx.ReadTimeout):client.get('https://example.invalid')
    assert calls==[1]
