"""Explicit offline resource owner. No credentials, transport configuration or launcher."""
from threading import Event, Lock
from fastapi.responses import JSONResponse

from .pilot_conversation import PilotConversation
from .pilot_delivery import DeliveryPool
from .pilot_execution import BoundedDelegator, PilotScheduler, _seconds
from .pilot_inbox import PilotInbox
from .pilot_runtime import PilotWorker
from .pilot_telegram import create_app


class PilotLifecycle:
    def __init__(self, path, bindings, policy, *, delegator_factory, send,
                 webhook_secret, allowed_host, global_limit, carrier_limit,
                 provider_timeout, interval, transport_clients=()):
        self._lock = Lock()
        self._close_lock = Lock()
        self._closing = False
        self._started = False
        self._clients = list(transport_clients)
        self._requests = 0
        self._requests_drained = Event();self._requests_drained.set()
        self.inbox = PilotInbox(path, bindings, policy)
        self.provider = None
        try:
            self.provider = BoundedDelegator(delegator_factory(self.inbox),timeout=provider_timeout)
            self.delivery = DeliveryPool(None)
            self.inbox._delivery_pool = self.delivery
            self.worker = PilotWorker(self.inbox,self.provider,send,
                global_limit=global_limit,carrier_limit=carrier_limit)
            self.scheduler = PilotScheduler(self.worker,interval=interval)
            self._app = create_app(self.inbox,webhook_secret=webhook_secret,
                allowed_host=allowed_host,conversation=PilotConversation(self.inbox),send=send)
        except Exception:
            if self.provider is not None:self.provider.close()
            try:
                for client in self._clients:client.close()
            finally:self.inbox.close()
            raise

    def start(self):
        with self._lock:
            if self._closing or self._started:raise RuntimeError('Lifecycle cannot restart')
            self._started = True
            self.scheduler.start()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self._app(scope,receive,send)
        with self._lock:
            rejected = self._closing
            if not rejected:
                self._requests += 1
                self._requests_drained.clear()
        if rejected:
            return await JSONResponse({'status':'unavailable'},status_code=503,
                headers={'Cache-Control':'no-store'})(scope,receive,send)
        try:return await self._app(scope,receive,send)
        finally:
            with self._lock:
                self._requests -= 1
                if self._requests == 0:self._requests_drained.set()

    def close(self, *, timeout):
        _seconds(timeout)
        if not self._close_lock.acquire(blocking=False):
            raise RuntimeError('Shutdown already in progress')
        try:
            with self._lock:self._closing = True
            scheduler = self.scheduler.close(timeout=timeout)
            self.provider.close()
            self.delivery.close()
            status = dict(scheduler=scheduler,provider=self.provider.drained,
                          sender=self.delivery.drained,
                          requests=self._requests_drained.is_set())
            if all(status.values()) and not self.inbox._closed:
                while self._clients:
                    try:self._clients[0].close()
                    except Exception:raise RuntimeError('Transport cleanup incomplete') from None
                    self._clients.pop(0)
                self.inbox.close()
            status['storage_released'] = self.inbox._closed
            return status
        finally:
            self._close_lock.release()
