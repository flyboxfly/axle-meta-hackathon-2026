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
