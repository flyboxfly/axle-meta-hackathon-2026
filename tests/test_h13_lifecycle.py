from threading import Event
import httpx
import asyncio
import pytest
from axle_hackathon.pilot_lifecycle import PilotLifecycle
from axle_hackathon.pilot_inbox import PilotInbox
from axle_hackathon.pilot_memory import MemoryPolicy
from test_h13_telegram import ready,SECRET,update


def owner(tmp_path, factory, send=lambda *_:True):
    return PilotLifecycle(tmp_path/'owned.sqlite3',{(1,1):'a'},
        MemoryPolicy(version='test',processing_notice='Invented offline data'),
        delegator_factory=factory,send=send,webhook_secret=SECRET,allowed_host='testserver',
        global_limit=2,carrier_limit=2,provider_timeout=.03,interval=.01)


@pytest.mark.parametrize('blocked',['provider','sender'])
def test_timeout_retains_storage_owner_until_actual_exit(tmp_path,blocked):
    started,release=Event(),Event()
    def factory(s):
        class D:
            def evaluate(self,*args):
                if blocked=='provider':started.set();assert release.wait(2)
                return {'evaluation':s.evaluate(*args)}
        return D()
    def send(*args):started.set();assert release.wait(2);return True
    life=owner(tmp_path,factory,send if blocked=='sender' else lambda *_:True)
    if blocked=='sender':life.delivery._timeout=.03
    closed_clients=[]
    class Client:
        def close(self):closed_clients.append(1)
    life._clients.append(Client())
    s=life.inbox;a=ready(s)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    try:
        assert life.worker.tick()=='uncertain' and started.is_set()
        status=life.close(timeout=.1)
        assert status['scheduler'] and not status[blocked] and not status['storage_released']
        assert closed_clients==[]
        with pytest.raises(RuntimeError,match='already has an owner'):
            PilotInbox(tmp_path/'owned.sqlite3',{(1,1):'a'},s._policy)
        with pytest.raises(RuntimeError):life.start()
    finally:
        release.set()
        life.provider._executor.shutdown(wait=True)
        life.delivery._executor.shutdown(wait=True)
        status=life.close(timeout=1)
    assert all(status.values()) and closed_clients==[1]
    replacement=PilotInbox(tmp_path/'owned.sqlite3',{(1,1):'a'},s._policy)
    replacement.close()


def test_closed_owner_rejects_requests_and_restart(tmp_path):
    life=owner(tmp_path,lambda s:None)
    life.start()
    assert all(life.close(timeout=1).values())
    with pytest.raises(RuntimeError):life.start()
    async def post():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=life),base_url='http://testserver') as c:
            return await c.post('/telegram/webhook',json=update('/start',id=1),
                headers={'X-Telegram-Bot-Api-Secret-Token':SECRET})
    assert asyncio.run(post()).status_code==503


def test_partial_construction_releases_database_owner(tmp_path):
    with pytest.raises(ValueError):
        PilotLifecycle(tmp_path/'owned.sqlite3',{(1,1):'a'},
            MemoryPolicy(version='test',processing_notice='Invented offline data'),
            delegator_factory=lambda s:None,send=lambda *_:True,webhook_secret=SECRET,
            allowed_host='testserver',global_limit=0,carrier_limit=1,provider_timeout=1,interval=1)
    life=owner(tmp_path,lambda s:None)
    assert life.close(timeout=1)['storage_released']


def test_active_request_prevents_storage_release(tmp_path,monkeypatch):
    import axle_hackathon.pilot_telegram as telegram
    life=owner(tmp_path,lambda s:None)
    async def exercise():
        entered,release=asyncio.Event(),asyncio.Event()
        async def blocked(*args):
            entered.set();await release.wait();raise RuntimeError('invented failure')
        monkeypatch.setattr(telegram.asyncio,'to_thread',blocked)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=life),base_url='http://testserver') as c:
            task=asyncio.create_task(c.post('/telegram/webhook',json=update('/start',id=1),
                headers={'X-Telegram-Bot-Api-Secret-Token':SECRET}))
            try:
                await asyncio.wait_for(entered.wait(),1)
                status=life.close(timeout=.01)
                assert not status['requests'] and not status['storage_released']
            finally:
                release.set();await task
        assert all(life.close(timeout=1).values())
    try:asyncio.run(exercise())
    finally:life.close(timeout=1)


def test_shutdown_wait_does_not_block_request_rejection(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    life=owner(tmp_path,lambda s:None);entered,release=Event(),Event()
    original=life.scheduler.close
    def delayed_close(*,timeout):
        entered.set();assert release.wait(2)
        return original(timeout=timeout)
    monkeypatch.setattr(life.scheduler,'close',delayed_close)
    async def post():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=life),base_url='http://testserver') as c:
            return await c.post('/telegram/webhook',json=update('/start',id=1))
    with ThreadPoolExecutor(max_workers=2) as pool:
        closing=pool.submit(life.close,timeout=1)
        try:
            assert entered.wait(1)
            with pytest.raises(RuntimeError,match='Shutdown already in progress'):
                life.close(timeout=.01)
            request=pool.submit(asyncio.run,post())
            assert request.result(timeout=.3).status_code==503
        finally:release.set()
        assert closing.result(timeout=1)['storage_released']
