"""Bounded injected delivery attempts; no real messaging client or retries."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore


class DeliveryPool:
    def __init__(self, send, *, timeout=5, workers=2):
        self._send, self._timeout = send, timeout
        self._slots = BoundedSemaphore(workers)
        self._executor = ThreadPoolExecutor(max_workers=workers,thread_name_prefix='pilot-send')

    def send(self, chat, text, guard, sender=None):
        if not self._slots.acquire(blocking=False):
            raise RuntimeError('Delivery capacity reached')
        def attempt():
            try:
                guard()  # Fresh authorization and durable sending marker at dispatch.
                if (sender or self._send)(chat,text) is not True:
                    raise RuntimeError('Delivery not confirmed')
            finally:
                self._slots.release()
        try:
            future=self._executor.submit(attempt)
        except Exception:
            self._slots.release()
            raise RuntimeError('Delivery unavailable') from None
        try:
            future.result(timeout=self._timeout)
        except Exception:
            # Timed-out I/O may still complete. Its slot stays occupied until it exits.
            raise RuntimeError('Delivery uncertain; no automatic retry') from None

    def close(self):
        self._executor.shutdown(wait=False,cancel_futures=False)
