"""Explicit ASGI host adapter; no launcher, secrets or live transport wiring."""
import asyncio
from fastapi.responses import JSONResponse
from .pilot_execution import _seconds


class PilotHost:
    def __init__(self, owner, *, shutdown_timeout):
        self.owner = owner
        self._timeout = _seconds(shutdown_timeout)
        self._state = 'new'
        self.last_shutdown = None
        self._shutdown_task = None

    async def finish_shutdown(self):
        """Inspect again after incomplete drain; never create replacement resources."""
        if self._state not in ('closing','failed','closed'):
            raise RuntimeError('Shutdown has not begun')
        if self._shutdown_task is None or self._shutdown_task.done():
            self._shutdown_task = asyncio.create_task(self._close_owner())
            # Keep errors observed even if every waiting caller is cancelled.
            self._shutdown_task.add_done_callback(
                lambda task: None if task.cancelled() else task.exception())
        return await asyncio.shield(self._shutdown_task)

    async def _close_owner(self):
        status = await asyncio.to_thread(self.owner.close,timeout=self._timeout)
        self.last_shutdown = status
        self._state = 'closed' if all(status.values()) else 'closing'
        return status

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            if self._state != 'new':
                await send({'type':'lifespan.startup.failed','message':'Host cannot restart'})
                raise RuntimeError('Host cannot restart')
            self._state = 'initializing'
            try:
                return await self._lifespan(receive,send)
            except BaseException:
                if self._state in ('initializing','starting','running'):
                    self._state = 'closing'
                    try:await self.finish_shutdown()
                    except BaseException:pass  # Retained shutdown task survives caller cancellation.
                raise
        if scope['type'] == 'http' and self._state != 'running':
            return await JSONResponse({'status':'unavailable'},status_code=503,
                headers={'Cache-Control':'no-store'})(scope,receive,send)
        return await self.owner(scope,receive,send)

    async def _lifespan(self, receive, send):
        message = await receive()
        if message['type'] != 'lifespan.startup' or self._state != 'initializing':
            await send({'type':'lifespan.startup.failed','message':'Host cannot restart'})
            raise RuntimeError('Host cannot restart')
        self._state = 'starting'
        try:await asyncio.to_thread(self.owner.start)
        except Exception:
            self._state = 'failed'
            try:await self.finish_shutdown()
            except Exception:pass
            await send({'type':'lifespan.startup.failed','message':'Pilot startup failed'})
            raise RuntimeError('Pilot startup failed') from None
        self._state = 'running'
        await send({'type':'lifespan.startup.complete'})
        message = await receive()
        if message['type'] != 'lifespan.shutdown':
            self._state = 'closing'
            await self.finish_shutdown()
            return
        self._state = 'closing'
        try:
            status = await self.finish_shutdown()
        except Exception:
            await send({'type':'lifespan.shutdown.failed','message':'Pilot shutdown incomplete'})
            raise RuntimeError('Pilot shutdown incomplete') from None
        if all(status.values()):await send({'type':'lifespan.shutdown.complete'})
        else:
            await send({'type':'lifespan.shutdown.failed','message':'Pilot work still draining; owner retained'})
            raise RuntimeError('Pilot work still draining; owner retained')
        return
