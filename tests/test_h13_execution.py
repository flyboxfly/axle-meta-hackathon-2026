from threading import Event
import pytest
from axle_hackathon.pilot_execution import BoundedDelegator, PilotScheduler
from axle_hackathon.pilot_runtime import PilotWorker
from test_h13_inbox import inbox
from test_h13_telegram import ready


def test_provider_timeout_retains_capacity_and_late_result_is_not_delivered(inbox):
    s,_,_=inbox;a=ready(s);started,release=Event(),Event();sent=[];calls=[]
    class D:
        def evaluate(self,*args):
            calls.append(1);started.set();assert release.wait(2)
            return {'evaluation':s.evaluate(*args)}
    bounded=BoundedDelegator(D(),timeout=.05)
    w=PilotWorker(s,bounded,lambda *args:sent.append(args) or True,global_limit=3,carrier_limit=3)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    try:
        assert w.tick()=='uncertain' and started.is_set()
        s.submit(1,1,2,'evaluate',token=a.token,revision=1)
        assert w.tick()=='uncertain' and calls==[1]
    finally:
        release.set();bounded.close();bounded._executor.shutdown(wait=True)
    assert sent==[]
    assert s._db.execute('SELECT status FROM pilot_updates').fetchall()==[('uncertain',),('uncertain',)]
    assert w.tick()=='idle'
    with pytest.raises(RuntimeError,match='unavailable'):bounded.evaluate()


def test_scheduler_stop_interrupts_wait_and_is_terminal():
    ticked=Event()
    class W:
        def tick(self):ticked.set();return 'idle'
        def close(self):pass
    scheduler=PilotScheduler(W(),interval=60)
    scheduler.start()
    assert ticked.wait(1)
    assert scheduler.close(timeout=.5)
    with pytest.raises(RuntimeError):scheduler.start()


def test_scheduler_reports_incomplete_drain_without_replacing_work():
    started,release=Event(),Event();calls=[]
    class W:
        def tick(self):
            calls.append(1);started.set();assert release.wait(2);return 'idle'
        def close(self):pass
    scheduler=PilotScheduler(W(),interval=.01)
    scheduler.start()
    try:
        assert started.wait(1)
        assert not scheduler.close(timeout=.02)
        with pytest.raises(RuntimeError):scheduler.start()
    finally:release.set()
    assert scheduler.close(timeout=1) and calls==[1]


@pytest.mark.parametrize('value',[0,-1,float('inf'),float('nan'),True])
def test_execution_rejects_unbounded_wait_configuration(value):
    with pytest.raises(ValueError):BoundedDelegator(None,timeout=value)
    with pytest.raises(ValueError):PilotScheduler(None,interval=value)


def test_stalled_flow_admission_keeps_forget_available(inbox,monkeypatch):
    import asyncio
    import httpx
    import axle_hackathon.pilot_telegram as telegram
    from axle_hackathon.pilot_conversation import PilotConversation
    from test_h13_telegram import SECRET,update
    s,_,_=inbox
    async def exercise():
        entered=asyncio.Queue();release=asyncio.Event()
        async def blocked(*args):
            entered.put_nowait(True)
            await release.wait()
            raise RuntimeError('invented stalled delivery')
        monkeypatch.setattr(telegram.asyncio,'to_thread',blocked)
        app=telegram.create_app(s,webhook_secret=SECRET,allowed_host='testserver',
            conversation=PilotConversation(s),send=lambda *_:True)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:
            async def post(text,id):
                return await c.post('/telegram/webhook',json=update(text,id=id),
                    headers={'X-Telegram-Bot-Api-Secret-Token':SECRET})
            tasks=[]
            try:
                for id in (1,2):
                    tasks.append(asyncio.create_task(post('/start',id)))
                    await asyncio.wait_for(entered.get(),1)
                assert (await post('/start',3)).status_code==503
                assert s._db.execute('SELECT count(*) FROM pilot_updates').fetchone()==(2,)
                assert (await post('/forget',4)).status_code==200
                assert not s._conversation_states
            finally:
                release.set()
                await asyncio.gather(*tasks)
            # Admission was released even on delivery failure.
            assert (await post('/start',5)).status_code==503
            assert s._db.execute('SELECT count(*) FROM pilot_updates').fetchone()==(3,)
    asyncio.run(exercise())


def test_scheduler_close_does_not_wait_for_inbox_lock(inbox):
    from concurrent.futures import ThreadPoolExecutor
    s,_,_=inbox
    class D:
        def evaluate(self,*args):raise AssertionError('No model work expected')
    w=PilotWorker(s,D(),lambda *_:True,global_limit=1,carrier_limit=1)
    scheduler=PilotScheduler(w,interval=1)
    # A database operation may hold this lock. Shutdown's deadline must still apply.
    with ThreadPoolExecutor(max_workers=1) as pool:
        with s._lock:
            closing=pool.submit(scheduler.close,timeout=.05)
            assert closing.result(timeout=.3)
    assert w.tick()=='closed'


def test_scheduler_reports_incomplete_drain_for_tick_waiting_on_storage(inbox):
    from concurrent.futures import ThreadPoolExecutor
    s,_,_=inbox;entered=Event()
    class W(PilotWorker):
        def tick(self):entered.set();return super().tick()
    w=W(s,None,None,global_limit=1,carrier_limit=1)
    scheduler=PilotScheduler(w,interval=1)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with s._lock:
                scheduler.start()
                assert entered.wait(1)
                closing=pool.submit(scheduler.close,timeout=.05)
                assert closing.result(timeout=.3) is False
    finally:
        assert scheduler.close(timeout=1)
    assert scheduler.last_status=='closed'
