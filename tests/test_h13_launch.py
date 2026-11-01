import asyncio
import json
import os
import pytest
import axle_hackathon.pilot_launch as launch
from test_h13_telegram import SECRET
from test_h13_transports import TOKEN


def config(tmp_path):
    tmp_path.chmod(0o700);path=tmp_path/'private.json'
    path.write_text(json.dumps(dict(approved_synthetic_owner_test=True,provider_key='invented',
        bot_token=TOKEN,webhook_secret=SECRET,allowed_host='testserver',user_id=1,chat_id=1)))
    path.chmod(0o600);return path


def test_private_config_accepts_exact_owner_binding(tmp_path):
    path=config(tmp_path);data,db=launch.read_private_config(path)
    assert data['user_id']==1 and db==tmp_path/'pilot.sqlite3'


@pytest.mark.parametrize('case',['mode','symlink','unapproved','duplicate'])
def test_private_config_rejects_unsafe_inputs_without_echo(tmp_path,case):
    path=config(tmp_path)
    if case=='mode':path.chmod(0o644)
    elif case=='symlink':
        alias=tmp_path/'alias';alias.symlink_to(path);path=alias
    elif case=='unapproved':path.write_text(path.read_text().replace('true','false'))
    else:path.write_text(path.read_text()[:-1]+',"user_id":2}')
    with pytest.raises(RuntimeError,match='^Private pilot configuration rejected$'):
        launch.read_private_config(path)


def test_server_is_single_loopback_and_retains_incomplete_owner(monkeypatch):
    settings={};calls=[]
    monkeypatch.setattr(launch.uvicorn,'Config',lambda app,**kwargs:settings.update(kwargs))
    class Server:
        def __init__(self,config):self.started=True
        async def serve(self):pass
    class Owner:
        def close(self,**kwargs):calls.append(1);return {'storage_released':len(calls)>1}
    class Host:owner=Owner()
    async def no_wait(seconds):pass
    monkeypatch.setattr(launch,'PrivateServer',Server)
    monkeypatch.setattr(launch.asyncio,'sleep',no_wait)
    asyncio.run(launch.serve_host(Host()))
    assert settings['host']=='127.0.0.1' and settings['workers']==1
    assert settings['proxy_headers'] is False and settings['access_log'] is False
    assert settings['limit_concurrency']==16 and len(calls)==2


@pytest.mark.parametrize('started',[True,False])
def test_graceful_signals_remain_owned_through_drain(monkeypatch,started):
    handlers={sig:object() for sig in (launch.signal.SIGINT,launch.signal.SIGTERM)}
    previous=handlers.copy();events=[]
    def install(sig,handler):
        old=handlers[sig];handlers[sig]=handler;return old
    monkeypatch.setattr(launch.signal,'signal',install)
    monkeypatch.setattr(launch.signal,'getsignal',lambda sig:handlers[sig])
    def no_replay(sig):pytest.fail('Graceful signal replay bypasses drain')
    monkeypatch.setattr(launch.signal,'raise_signal',no_replay)
    async def serve(server):
        server.started=started
        with server.capture_signals():
            handlers[launch.signal.SIGTERM](launch.signal.SIGTERM,None)
        assert server.should_exit and not server.force_exit
        events.append('server')
    monkeypatch.setattr(launch.PrivateServer,'serve',serve)
    class Owner:
        def close(self,**kwargs):
            assert all(callable(handler) for handler in handlers.values())
            handlers[launch.signal.SIGINT](launch.signal.SIGINT,None)
            events.append('drain')
            return {'storage_released':True}
    class Host:owner=Owner()
    if started:asyncio.run(launch.serve_host(Host()))
    else:
        with pytest.raises(RuntimeError,match='Pilot server did not start'):
            asyncio.run(launch.serve_host(Host()))
    assert events==['server','drain'] and handlers==previous


def test_private_config_checks_actual_bytes_after_stat(tmp_path,monkeypatch):
    from types import SimpleNamespace
    path=config(tmp_path)
    path.write_text(path.read_text().ljust(8193))
    real_fstat=os.fstat
    def old_size(fd):
        info=real_fstat(fd)
        return SimpleNamespace(st_mode=info.st_mode,st_uid=info.st_uid,st_size=8192)
    monkeypatch.setattr(launch.os,'fstat',old_size)
    with pytest.raises(RuntimeError,match='^Private pilot configuration rejected$'):
        launch.read_private_config(path)
