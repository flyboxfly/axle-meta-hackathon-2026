"""Bounded offline execution wrappers; injected operations must enforce HTTP deadlines."""
from concurrent.futures import ThreadPoolExecutor
from math import isfinite
from threading import BoundedSemaphore, Event, Lock, Thread


def _seconds(value):
    if type(value) not in (int, float) or not isfinite(value) or value <= 0:
        raise ValueError('Finite positive seconds required')
    return value


class BoundedDelegator:
    """One provider operation at a time, with a bounded caller wait and no retries.

    Timeout cannot kill Python I/O. Capacity remains occupied until actual exit;
    late results are discarded. The injected client's HTTP deadlines remain required.
    """
    def __init__(self, delegator, *, timeout):
        self._timeout = _seconds(timeout)
        self._delegator = delegator
        self._slot = BoundedSemaphore(1)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pilot-model')

    def evaluate(self, *args):
        if not self._slot.acquire(blocking=False):
            raise RuntimeError('Provider capacity reached')
        def attempt():
            try:return self._delegator.evaluate(*args)
            finally:self._slot.release()
        try:future = self._executor.submit(attempt)
        except Exception:
            self._slot.release()
            raise RuntimeError('Provider unavailable') from None
        try:return future.result(timeout=self._timeout)
        except Exception:
            raise RuntimeError('Provider outcome uncertain; no automatic retry') from None

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=False)


class PilotScheduler:
    """Explicitly started single loop; stop interrupts idle waits, never retries tasks."""
    def __init__(self, worker, *, interval):
        self._interval = _seconds(interval)
        self._worker = worker
        self._stop = Event()
        self._lock = Lock()
        self._thread = None
        self._closed = False
        self.last_status = 'new'  # Bounded status only; never exception/payload text.

    def start(self):
        with self._lock:
            if self._closed or self._thread is not None:
                raise RuntimeError('Scheduler cannot restart')
            self._thread = Thread(target=self._run, name='pilot-scheduler', daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:self.last_status = self._worker.tick()
            except Exception:self.last_status = 'unavailable'
            if self.last_status == 'closed':return
            self._stop.wait(self._interval)

    def close(self, *, timeout):
        timeout = _seconds(timeout)
        with self._lock:
            self._closed = True
            self._stop.set()
            self._worker.close()
            thread = self._thread
        if thread is not None:thread.join(timeout)
        return thread is None or not thread.is_alive()
