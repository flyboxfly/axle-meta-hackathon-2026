from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from axle_hackathon.pilot_telegram import create_app, run_evaluation
from axle_hackathon.pilot_meta import PilotDelegator
from test_h13_inbox import inbox
from test_h13_memory import consent, confirmed
from test_h13_pilot import profile, offer
from test_h13_meta import response

SECRET='test_secret_'+'x'*32


def client(s):
    return TestClient(create_app(s,webhook_secret=SECRET,allowed_host='testserver'))


def update(command='/evaluate', uid=1, id=100, kind='private'):
    return dict(update_id=id,message={'from':dict(id=uid,is_bot=False),
        'chat':dict(id=uid,type=kind),'text':command})


def ready(s):
    a=consent(s)
    s.put(1,1,a.token,profile(),offer(origin='synthetic'),expected_revision=0)
    s.confirm(1,1,a.token,1)
    return a


def test_authenticated_webhook_to_worker_with_mocked_model_and_send(inbox):
    s,_,_=inbox;ready(s);c=client(s)
    headers={'X-Telegram-Bot-Api-Secret-Token':SECRET}
    assert c.post('/telegram/webhook',json=update(),headers=headers).json()['status']=='queued'
    calls=[]; sent=[]
    def model(**kw): calls.append(kw);return response()
    def send(chat,text): sent.append((chat,text));return True
    d=PilotDelegator(s,NS(responses=NS(create=model)))
    run_evaluation(s,d,send,user=1,chat=1,update_id=100)
    assert len(calls)==1 and sent[0][0]==1 and 'NEGOTIATE' in sent[0][1]
    assert c.post('/telegram/webhook',json=update(),headers=headers).json()['status']=='duplicate'
    with pytest.raises(ValueError):run_evaluation(s,d,send,user=1,chat=1,update_id=100)
    assert len(calls)==1 and len(sent)==1


@pytest.mark.parametrize('payload,secret,status',[
    (update(),None,403),(update(), 'bad',403),
    (update(uid=3),SECRET,403),(update(kind='group'),SECRET,403),
    (update('/something'),SECRET,400),({'update_id':1},SECRET,400)])
def test_rejection_before_queue(inbox,payload,secret,status):
    s,_,_=inbox
    headers={} if secret is None else {'X-Telegram-Bot-Api-Secret-Token':secret}
    assert client(s).post('/telegram/webhook',json=payload,headers=headers).status_code==status
    assert s._db.execute('SELECT count(*) FROM pilot_updates').fetchone()[0]==0


def test_size_host_and_duplicate_json_rejected(inbox):
    s,_,_=inbox;c=client(s);headers={'X-Telegram-Bot-Api-Secret-Token':SECRET}
    assert c.post('/telegram/webhook',content='x'*8193,headers=headers).status_code==413
    assert c.post('/telegram/webhook',json=update(),headers={**headers,'host':'wrong'}).status_code==403
    assert c.post('/telegram/webhook',content='{"update_id":1,"update_id":2}',headers=headers).status_code==400


def test_forget_and_duplicate_after_consent_withdrawn(inbox):
    s,_,_=inbox;a=ready(s);c=client(s);headers={'X-Telegram-Bot-Api-Secret-Token':SECRET}
    c.post('/telegram/webhook',json=update(),headers=headers)
    assert c.post('/telegram/webhook',json=update('/forget',id=101),headers=headers).status_code==200
    with pytest.raises(PermissionError):s.get(1,1,a.token)
    assert c.post('/telegram/webhook',json=update(),headers=headers).json()['status']=='duplicate'
    s.process_forget(1,1,101)


@pytest.mark.parametrize('change',['forget','edit','delivery_failure'])
def test_worker_does_not_deliver_stale_results_or_retry(inbox,change):
    s,_,_=inbox;a=ready(s)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    sends=[]
    class FakeDelegator:
        def evaluate(self,*args):
            result=s.evaluate(*args)
            if change=='forget':s.forget(1,1)
            if change=='edit':s.put(1,1,a.token,profile(),offer(origin='synthetic',payout='800'),expected_revision=1)
            return {'evaluation':result}
    def send(chat,text):sends.append(text);raise RuntimeError('private token URL')
    with pytest.raises(RuntimeError,match='^Worker failed; outcome uncertain; no automatic retry$'):
        run_evaluation(s,FakeDelegator(),send,user=1,chat=1,update_id=1)
    assert len(sends)==(1 if change=='delivery_failure' else 0)
    assert s._db.execute('SELECT status FROM pilot_updates').fetchone()[0]=='uncertain'
