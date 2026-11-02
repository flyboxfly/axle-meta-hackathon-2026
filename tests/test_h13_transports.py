import json
import httpx
import pytest
from axle_hackathon.pilot_transports import MetaResponsesClient,TelegramSender
from axle_hackathon.pilot_meta import PilotDelegator
from axle_hackathon.pilot_runtime import PilotWorker
from test_h13_inbox import inbox
from test_h13_telegram import ready

TOKEN='123:'+('x'*30)

def response(status,*,json_value=None,content=b'',headers=None):
    raw=json.dumps(json_value).encode() if json_value is not None else content
    return httpx.Response(status,stream=httpx.ByteStream(raw),headers=headers)



def test_full_worker_uses_http_provider_and_sender_with_invented_data(inbox):
    s,_,_=inbox;a=ready(s);calls=[]
    def handle(request):
        payload=json.loads(request.content);calls.append(request.url.host)
        if request.url.host=='api.meta.ai':
            assert 'profile' not in payload['input'] and a.token not in payload['input']
            return response(200,json_value={'status':'completed','output':[{'type':'function_call',
                'status':'completed','name':'review_confirmed_planning','arguments':'{"revision":1}'}]})
        assert set(payload)=={'chat_id','text'} and payload['chat_id']==1
        return response(200,json_value={'ok':True,'result':{'message_id':1,'chat':{'id':1,'type':'private'}}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        d=PilotDelegator(s,MetaResponsesClient(c,'invented-key',seconds=1))
        send=TelegramSender(c,TOKEN,allowed_chats={1},seconds=1)
        w=PilotWorker(s,d,send,global_limit=1,carrier_limit=1)
        s.submit(1,1,1,'evaluate',token=a.token,revision=1)
        assert w.tick()=='completed'
        assert w.tick()=='idle'
    assert calls==['api.meta.ai','api.telegram.org']


@pytest.mark.parametrize('kind',['oversize','duplicate','timeout','redirect'])
def test_transport_failures_are_bounded_sanitized_and_single_attempt(kind):
    calls=[]
    def handle(request):
        calls.append(1)
        if kind=='timeout':raise httpx.ReadTimeout('invented-secret '+TOKEN)
        if kind=='redirect':return response(302,headers={'location':'https://example.invalid'})
        return response(200,content=b'x'*70000 if kind=='oversize' else b'{"ok":true,"ok":false}')
    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        send=TelegramSender(c,TOKEN,allowed_chats={1},seconds=1)
        with pytest.raises(RuntimeError) as exc:send(1,'invented')
        assert TOKEN not in str(exc.value) and 'invented-secret' not in str(exc.value)
        with pytest.raises(PermissionError):send(2,'invented')
    assert calls==[1]


@pytest.mark.parametrize('chat',[None,[],{'id':True,'type':'private'},{'id':1.0,'type':'private'}])
def test_malformed_chat_acknowledgement_is_never_success(chat):
    with httpx.Client(transport=httpx.MockTransport(lambda request:response(200,json_value={
            'ok':True,'result':{'message_id':1,'chat':chat}}))) as c:
        with pytest.raises(RuntimeError,match='^Delivery uncertain; no automatic retry$'):
            TelegramSender(c,TOKEN,allowed_chats={1},seconds=1)(1,'invented')
