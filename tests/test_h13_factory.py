import json
from threading import Event
import httpx
import pytest
from fastapi.testclient import TestClient
import axle_hackathon.pilot_factory as factory
from axle_hackathon.pilot_memory import MemoryPolicy
from test_h13_telegram import SECRET,update
from test_h13_transports import TOKEN,response


def build(tmp_path):
    return factory.build_synthetic_host(tmp_path/'fixed.sqlite3',{(1,1):'a'},
        MemoryPolicy(version='test',processing_notice='Invented synthetic records only'),
        provider_key='invented-key',bot_token=TOKEN,webhook_secret=SECRET,
        allowed_host='testserver',global_limit=2,carrier_limit=1)


def test_full_host_http_rehearsal_and_shutdown(tmp_path,monkeypatch):
    clients=[];sent=[];models=[];delivered=Event()
    def handle(request):
        payload=json.loads(request.content)
        if request.url.host=='api.meta.ai':
            models.append(payload)
            return response(200,json_value={'status':'completed','output':[{'type':'function_call',
                'status':'completed','name':'review_confirmed_planning','arguments':'{"revision":1}'}]})
        sent.append(payload['text'])
        if 'NEGOTIATE' in sent[-1]:delivered.set()
        return response(200,json_value={'ok':True,'result':{'message_id':len(sent),
            'chat':{'id':1,'type':'private'}}})
    def client(**kwargs):
        c=httpx.Client(transport=httpx.MockTransport(handle));clients.append(c);return c
    monkeypatch.setattr(factory,'create_http_client',client)
    host=build(tmp_path)
    with TestClient(host) as c:
        def post(text,id):
            r=c.post('/telegram/webhook',json=update(text,id=id),
                     headers={'X-Telegram-Bot-Api-Secret-Token':SECRET})
            assert r.status_code==200
            return r
        post('/start',1)
        for id,answer in enumerate(['session','box_truck_26ft owned','420 180 40','20 6 feasible','2','1.25'],2):
            nonce=sent[-1].split('\nStep: ')[1].split('\n')[0]
            post(f'/reply {nonce} {answer}',id)
        nonce=sent[-1].split('\nStep: ')[1].split('\n')[0]
        post(f'/confirm {nonce}',8);post('/evaluate',9)
        assert delivered.wait(3)
        assert post('/evaluate',9).json()['status']=='duplicate'
        assert len(models)==1
        assert any('$300.00' in text for text in sent)
        post('/forget',10)
        assert not host.owner.inbox._active
    assert all(host.last_shutdown.values()) and all(c.is_closed for c in clients)


def test_factory_cleans_first_client_when_second_creation_fails(tmp_path,monkeypatch):
    clients=[]
    def client(**kwargs):
        if clients:raise RuntimeError('invented-private-detail')
        c=httpx.Client(transport=httpx.MockTransport(lambda r:None));clients.append(c);return c
    monkeypatch.setattr(factory,'create_http_client',client)
    with pytest.raises(RuntimeError,match='^Synthetic host construction failed; cleanup attempted$'):build(tmp_path)
    assert clients[0].is_closed


def test_failed_database_acquisition_cleans_both_new_clients(tmp_path,monkeypatch):
    clients=[]
    def client(**kwargs):
        c=httpx.Client(transport=httpx.MockTransport(lambda r:None));clients.append(c);return c
    monkeypatch.setattr(factory,'create_http_client',client)
    first=build(tmp_path)
    try:
        with pytest.raises(RuntimeError,match='^Synthetic host construction failed; cleanup attempted$'):build(tmp_path)
        assert all(c.is_closed for c in clients[2:])
        assert all(not c.is_closed for c in clients[:2])
    finally:first.owner.close(timeout=1)
