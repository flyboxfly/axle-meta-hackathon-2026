"""Track actual executor completion, including work outliving caller timeouts."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock


class TrackedExecutor(ThreadPoolExecutor):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tracking_lock = Lock()
        self._pending = 0
        self.drained = Event()
        self.drained.set()

    def submit(self, fn, /, *args, **kwargs):
        with self._tracking_lock:
            self._pending += 1
            self.drained.clear()
        def finished(_):
            with self._tracking_lock:
                self._pending -= 1
                if self._pending == 0:self.drained.set()
        try:future = super().submit(fn, *args, **kwargs)
        except BaseException:
            finished(None)
            raise
        future.add_done_callback(finished)
        return future
