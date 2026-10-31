from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from axle_hackathon.pilot_delivery import DeliveryPool
from axle_hackathon.pilot_telegram import run_evaluation
from test_h13_inbox import inbox
from test_h13_telegram import ready


def test_timed_out_send_retains_bounded_slot_until_actual_exit():
    started,release=Event(),Event();calls=[]
    def send(chat,text):started.set();release.wait(2);calls.append(text);return True
    pool=DeliveryPool(send,timeout=.02,workers=1)
    try:
        with pytest.raises(RuntimeError,match='uncertain'):pool.send(1,'test',lambda:None)
        assert started.is_set()
        with pytest.raises(RuntimeError,match='capacity'):pool.send(1,'again',lambda:None)
    finally:release.set();pool.close()


def test_withdrawal_can_complete_during_evaluation_send(inbox):
    s,_,_=inbox;a=ready(s)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    started,release=Event(),Event()
    class D:
        def evaluate(self,*args):return {'evaluation':s.evaluate(*args)}
    def send(chat,text):started.set();release.wait(2);return True
    with ThreadPoolExecutor(max_workers=2) as workers:
        result=workers.submit(run_evaluation,s,D(),send,user=1,chat=1,update_id=1)
        try:
            assert started.wait(1)
            withdrawal=workers.submit(s.forget,1,1)
            withdrawal.result(timeout=.5)
            with pytest.raises(PermissionError):s.get(1,1,a.token)
        finally:release.set()
        result.result(timeout=1) # Already-started send can finish; it cannot be recalled.


def test_invalid_answer_gets_safe_prompt_and_refresh_does_not_repeat_mutation(inbox):
    from fastapi.testclient import TestClient
    from axle_hackathon.pilot_conversation import PilotConversation
    from axle_hackathon.pilot_telegram import create_app
    from test_h13_telegram import SECRET,update
    s,_,_=inbox;f=PilotConversation(s);sent=[]
    def send(chat,text):sent.append(text);return True
    c=TestClient(create_app(s,webhook_secret=SECRET,allowed_host='testserver',conversation=f,send=send))
    def post(text,id):return c.post('/telegram/webhook',json=update(text,id=id),
        headers={'X-Telegram-Bot-Api-Secret-Token':SECRET})
    post('/start',1)
    step=f._flows['a']['nonce']
    assert post(f'/reply {step} invalid-private-value',2).status_code==200
    assert 'Please check your answer' in sent[-1] and 'invalid-private-value' not in sent[-1]
    assert f._flows['a']['nonce']==step
    assert post('/refresh',3).status_code==200
    assert f._flows['a']['nonce']==step
