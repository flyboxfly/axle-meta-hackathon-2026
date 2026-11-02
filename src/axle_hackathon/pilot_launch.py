"""Dedicated synthetic owner-test launcher candidate. Never import-starts a listener."""
import asyncio
from contextlib import contextmanager, nullcontext
import json
import logging
import os
from pathlib import Path
import stat
import signal
import threading
import sys
import uvicorn
from .pilot_factory import build_synthetic_host
from .pilot_memory import MemoryPolicy


def read_private_config(path):
    """POSIX private host directory; no secrets are accepted as command arguments."""
    try:
        path=Path(path)
        parent=path.parent.stat()
        if (not path.is_absolute() or parent.st_uid!=os.getuid()
                or stat.S_IMODE(parent.st_mode)!=0o700):raise ValueError()
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as file:
            info=os.fstat(file.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                    or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>8192):raise ValueError()
            def unique(pairs):
                value={}
                for key,item in pairs:
                    if key in value:raise ValueError()
                    value[key]=item
                return value
            raw=file.read(8193)
            if len(raw)>8192:raise ValueError()
            data=json.loads(raw,object_pairs_hook=unique)
        keys={'approved_synthetic_owner_test','provider_key','bot_token','webhook_secret',
              'allowed_host','user_id','chat_id'}
        if set(data)!=keys or data['approved_synthetic_owner_test'] is not True:raise ValueError()
        if any(type(data[k]) is not int or not 0<data[k]<2**53 for k in ('user_id','chat_id')):raise ValueError()
        if any(not isinstance(data[k],str) or not data[k] for k in
               ('provider_key','bot_token','webhook_secret','allowed_host')):raise ValueError()
        return data,path.parent/'pilot.sqlite3'
    except Exception:
        raise RuntimeError('Private pilot configuration rejected') from None


def configure_private_logging():
    # Dedicated process only. Blocks payload/URL/traceback logging, including child loggers.
    logging.disable(sys.maxsize)


class PrivateServer(uvicorn.Server):
    def capture_signals(self):
        # The launcher owns signals through drain; Uvicorn must not replay them.
        return nullcontext()


@contextmanager
def private_signals(server):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Pilot launcher requires the main thread')
    def stop(signum, frame):
        # Repeated graceful signals never bypass retained-owner cleanup.
        server.should_exit=True
    previous={}
    try:
        for sig in (signal.SIGINT,signal.SIGTERM):
            previous[sig]=signal.signal(sig,stop)
        yield
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


async def serve_host(host):
    config=uvicorn.Config(host,host='127.0.0.1',port=8013,workers=1,reload=False,
        lifespan='on',proxy_headers=False,access_log=False,log_config=None,
        ws='none',limit_concurrency=16,backlog=16,timeout_keep_alive=2,
        timeout_graceful_shutdown=6,h11_max_incomplete_event_size=8192)
    server=PrivateServer(config)
    with private_signals(server):
        try:
            await server.serve()
            if not server.started:raise RuntimeError('Pilot server did not start')
        finally:
            # Keep graceful signal handling installed until ownership is released.
            while True:
                try:status=await asyncio.to_thread(host.owner.close,timeout=6)
                except Exception:status={}
                if status and all(status.values()):break
                await asyncio.sleep(1)


def main():
    configure_private_logging()
    os.umask(0o077)
    try:
        data,path=read_private_config(os.environ.get('AXLE_PILOT_CONFIG_FILE',''))
        host=build_synthetic_host(path,{(data['user_id'],data['chat_id']):'owner'},
            MemoryPolicy(version='synthetic-owner-v1',processing_notice=
                'Synthetic owner test only. Use invented figures. Telegram and provider histories '
                'are separate; application session expires after one hour. /forget withdraws consent.'),
            provider_key=data['provider_key'],bot_token=data['bot_token'],
            webhook_secret=data['webhook_secret'],allowed_host=data['allowed_host'],
            global_limit=2,carrier_limit=2)
        asyncio.run(serve_host(host))
    except Exception:
        print('Pilot launcher stopped; inspect approved metadata-only recovery procedure.',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
