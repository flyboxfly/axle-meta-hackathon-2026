import asyncio
from threading import Event
from fastapi.testclient import TestClient
import httpx
import pytest
from axle_hackathon.pilot_host import PilotHost
from test_h13_lifecycle import owner
from test_h13_telegram import update


def test_host_starts_and_releases_owned_resources(tmp_path):
    life=owner(tmp_path,lambda s:None);host=PilotHost(life,shutdown_timeout=1)
    with TestClient(host) as c:
        assert c.post('/telegram/webhook',json=update('/forget',id=1)).status_code==403
        assert not life.inbox._closed
    assert all(host.last_shutdown.values())
    assert life.inbox._closed
    with pytest.raises(RuntimeError,match='cannot restart'):
        with TestClient(host):pass


def test_incomplete_shutdown_retains_owner_and_can_be_finished(tmp_path):
    started,release=Event(),Event()
    class D:
        def evaluate(self,*args):started.set();assert release.wait(2);return {}
    life=owner(tmp_path,lambda s:D());host=PilotHost(life,shutdown_timeout=.03)
    try:
        with pytest.raises(RuntimeError,match='still draining'):
            with TestClient(host):
                with pytest.raises(RuntimeError):life.provider.evaluate()
                assert started.is_set()
        assert not life.inbox._closed and not host.last_shutdown['provider']
    finally:
        release.set();life.provider._executor.shutdown(wait=True)
        assert all(asyncio.run(host.finish_shutdown()).values())


def test_shutdown_runs_off_event_loop_and_rejects_new_http():
    entered,release=Event(),Event()
    class Owner:
        def start(self):pass
        def close(self,**kwargs):
            entered.set();assert release.wait(2)
            return {'storage_released':True}
    host=PilotHost(Owner(),shutdown_timeout=1)
    async def exercise():
        incoming=asyncio.Queue();outgoing=asyncio.Queue()
        async def send(message):outgoing.put_nowait(message)
        task=asyncio.create_task(host({'type':'lifespan'},incoming.get,send))
        incoming.put_nowait({'type':'lifespan.startup'})
        assert (await asyncio.wait_for(outgoing.get(),1))['type']=='lifespan.startup.complete'
        incoming.put_nowait({'type':'lifespan.shutdown'})
        try:
            while not entered.is_set():await asyncio.sleep(.001)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host),base_url='http://testserver') as c:
                assert (await c.get('/')).status_code==503
        finally:release.set()
        await asyncio.wait_for(task,1)
        assert (await outgoing.get())['type']=='lifespan.shutdown.complete'
    asyncio.run(exercise())


def test_cancelled_lifespan_closes_admission_and_owner(tmp_path):
    life=owner(tmp_path,lambda s:None);host=PilotHost(life,shutdown_timeout=1)
    async def exercise():
        incoming=asyncio.Queue();started=asyncio.Event()
        async def send(message):
            if message['type']=='lifespan.startup.complete':started.set()
        incoming.put_nowait({'type':'lifespan.startup'})
        task=asyncio.create_task(host({'type':'lifespan'},incoming.get,send))
        await asyncio.wait_for(started.wait(),1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host),base_url='http://testserver') as c:
            assert (await c.get('/')).status_code==503
        assert life.inbox._closed
    try:asyncio.run(exercise())
    finally:life.close(timeout=1)


def test_shutdown_task_survives_caller_cancellation():
    entered,release=Event(),Event();calls=[]
    class Owner:
        def close(self,**kwargs):
            calls.append(1);entered.set();assert release.wait(2)
            return {'storage_released':True}
    host=PilotHost(Owner(),shutdown_timeout=1);host._state='closing'
    async def exercise():
        task=asyncio.create_task(host.finish_shutdown())
        try:
            assert await asyncio.to_thread(entered.wait,1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert not host._shutdown_task.cancelled()
        finally:release.set()
        assert all((await host.finish_shutdown()).values())
        assert calls==[1]
    asyncio.run(exercise())


def test_startup_failure_sanitizes_error_and_releases_owner(tmp_path,monkeypatch):
    life=owner(tmp_path,lambda s:None);host=PilotHost(life,shutdown_timeout=1)
    def fail():raise ValueError('invented-private-detail')
    monkeypatch.setattr(life,'start',fail)
    with pytest.raises(RuntimeError,match='^Pilot startup failed$'):
        with TestClient(host):pass
    assert life.inbox._closed
