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


def test_app_shutdown_cannot_replace_pool_with_inflight_delivery(inbox):
    import asyncio
    from axle_hackathon.pilot_telegram import create_app
    from test_h13_telegram import SECRET
    s,_,_=inbox
    app=create_app(s,webhook_secret=SECRET,allowed_host='testserver')
    pool=s._delivery_pool
    started,release=Event(),Event()
    def send(chat,text):
        started.set()
        assert release.wait(2)
        return True
    async def shutdown():
        async with app.router.lifespan_context(app):pass
    with ThreadPoolExecutor(max_workers=1) as workers:
        result=workers.submit(pool.send,1,'invented',lambda:None,send)
        try:
            assert started.wait(1)
            asyncio.run(shutdown())
            create_app(s,webhook_secret=SECRET,allowed_host='testserver')
            assert s._delivery_pool is pool
            with pytest.raises(RuntimeError,match='unavailable'):
                s._delivery_pool.send(1,'replacement',lambda:None,lambda *_:True)
        finally:release.set()
        result.result(timeout=1)


def test_cancelled_webhook_marks_pending_delivery_uncertain(inbox,monkeypatch):
    import asyncio
    import httpx
    import axle_hackathon.pilot_telegram as telegram
    from axle_hackathon.pilot_conversation import PilotConversation
    from test_h13_telegram import SECRET,update
    s,_,_=inbox;pending=[];sent=[]
    async def exercise():
        waiting=asyncio.Event()
        async def delayed_to_thread(fn,*args):
            pending.append((fn,args))
            waiting.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(telegram.asyncio,'to_thread',delayed_to_thread)
        app=telegram.create_app(s,webhook_secret=SECRET,allowed_host='testserver',
            conversation=PilotConversation(s),send=lambda *args:sent.append(args) or True)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:
            task=asyncio.create_task(c.post('/telegram/webhook',json=update('/start',id=1),
                headers={'X-Telegram-Bot-Api-Secret-Token':SECRET}))
            await asyncio.wait_for(waiting.wait(),1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(exercise())
    assert s._db.execute('SELECT status FROM pilot_updates WHERE update_id=1').fetchone()==('uncertain',)
    fn,args=pending[0]
    with pytest.raises(RuntimeError):fn(*args)
    assert sent==[]


def test_withdrawal_before_dispatch_prevents_sender_invocation(inbox):
    s,_,_=inbox;a=ready(s);sent=[]
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    waiting,release=Event(),Event()
    class DelayedPool(DeliveryPool):
        def send(self,chat,text,guard,sender=None):
            def delayed_guard():
                waiting.set()
                assert release.wait(2)
                guard()
            return super().send(chat,text,delayed_guard,sender)
    s._delivery_pool=DelayedPool(None)
    class D:
        def evaluate(self,*args):return {'evaluation':s.evaluate(*args)}
    with ThreadPoolExecutor(max_workers=1) as workers:
        result=workers.submit(run_evaluation,s,D(),lambda *args:sent.append(args) or True,
            user=1,chat=1,update_id=1)
        try:
            assert waiting.wait(1)
            s.forget(1,1)
        finally:release.set()
        with pytest.raises(RuntimeError,match='uncertain'):result.result(timeout=1)
    assert sent==[]
    assert s._db.execute('SELECT status FROM pilot_updates WHERE update_id=1').fetchone()==('uncertain',)


def test_late_sender_success_does_not_restore_timed_out_task(inbox):
    s,_,_=inbox;a=ready(s)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    s._delivery_pool=DeliveryPool(None,timeout=.05,workers=1)
    started,release=Event(),Event()
    class D:
        def evaluate(self,*args):return {'evaluation':s.evaluate(*args)}
    def send(*args):
        started.set()
        assert release.wait(2)
        return True
    try:
        with pytest.raises(RuntimeError,match='uncertain'):
            run_evaluation(s,D(),send,user=1,chat=1,update_id=1)
        assert started.is_set()
        assert s._db.execute('SELECT status FROM pilot_updates WHERE update_id=1').fetchone()==('uncertain',)
    finally:
        release.set()
        s._delivery_pool._executor.shutdown(wait=True)
    assert s._db.execute('SELECT status FROM pilot_updates WHERE update_id=1').fetchone()==('uncertain',)
