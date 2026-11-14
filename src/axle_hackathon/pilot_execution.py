"""Bounded offline execution wrappers; injected operations must enforce HTTP deadlines."""
from .pilot_tracking import TrackedExecutor
from math import isfinite
from threading import BoundedSemaphore, Event, Lock, Thread


def _seconds(value):
    if type(value) not in (int, float) or not isfinite(value) or value <= 0:
        raise ValueError('Finite positive seconds required')
    return value


# Sanitized failure categories only; exception text and payloads never persist.
FAILURE_CATEGORIES = frozenset({
    'provider_error', 'provider_timeout', 'provider_unavailable', 'invalid_model_response',
    'extraction_response_shape', 'extraction_incomplete', 'extraction_truncated',
    'extraction_filtered',
    'extraction_empty', 'extraction_json', 'extraction_schema', 'extraction_limits',
    'extraction_issues_count',
    'extraction_response_limit', 'extraction_collection_limit',
    'extraction_evidence_limit', 'extraction_issue_limit',
    'media_error', 'delivery_error', 'budget_exhausted',
    'consent_unavailable', 'stale_revision', 'missing_inputs', 'unknown'})



class ExtractionResponseError(RuntimeError):
    """An extraction failure with a fixed ledger category and no response data."""

    def __init__(self, category, message):
        super().__init__(message)
        self.failure_category = category


def failure_category_for(exc, *, stage=None):
    """Map one internal failure to a fixed category. No payload is retained."""
    if stage == 'delivery':
        return 'delivery_error'
    category = getattr(exc, 'failure_category', None)
    if category in FAILURE_CATEGORIES:
        return category
    message = str(exc)
    if isinstance(exc, PermissionError) or 'Current consent required' in message:
        return 'consent_unavailable'
    if 'Missing pricing inputs' in message:
        return 'missing_inputs'
    if 'Attempt budget exhausted' in message or 'budget' in message.lower():
        return 'budget_exhausted'
    if 'Invalid model' in message or 'Invalid provider response' in message:
        return 'invalid_model_response'
    if ('Media' in message or 'file size' in message or 'file reference' in message
            or 'PNG or JPEG' in message or 'Normalized image' in message):
        return 'media_error'
    if 'Model ' in message and 'failed' in message:
        return 'provider_error'
    if 'Remote outcome uncertain' in message:
        return 'provider_error'
    if ('Stale' in message or 'confirmed revision' in message
            or 'Result changed' in message or 'cannot be claimed' in message
            or isinstance(exc, KeyError)):
        return 'stale_revision'
    return 'unknown'


class BoundedDelegator:
    """One provider operation at a time, with a bounded caller wait and no retries.

    Timeout cannot kill Python I/O. Capacity remains occupied until actual exit;
    late results are discarded. The injected client's HTTP deadlines remain required.
    """
    def __init__(self, delegator, *, timeout):
        self._timeout = _seconds(timeout)
        self._delegator = delegator
        self._slot = BoundedSemaphore(1)
        self._executor = TrackedExecutor(max_workers=1, thread_name_prefix='pilot-model')

    def evaluate(self, *args):
        return self._run(self._delegator.evaluate, args, {})

    def extract(self, *args, **kwargs):
        if kwargs.get('admit') is not None:
            # A timed-out extraction must not publish a late draft.
            timed_out = Event()
            return self._run(self._delegator.extract, args,
                             {**kwargs, 'timed_out': timed_out}, timed_out=timed_out)
        return self._run(self._delegator.extract, args, kwargs)

    def select_pricing(self, *args, **kwargs):
        return self._run(self._delegator.select_pricing, args, kwargs)

    def _run(self, func, args, kwargs, *, timed_out=None):
        if not self._slot.acquire(blocking=False):
            raise RuntimeError('Provider capacity reached')
        def attempt():
            try:return func(*args, **kwargs)
            finally:self._slot.release()
        try:future = self._executor.submit(attempt)
        except Exception:
            self._slot.release()
            raise RuntimeError('Provider unavailable') from None
        try:return future.result(timeout=self._timeout)
        except TimeoutError:
            if timed_out is not None:
                timed_out.set()
            error = RuntimeError('Provider outcome uncertain; no automatic retry')
            error.failure_category = 'provider_timeout'
            raise error from None
        except Exception as exc:
            error = RuntimeError('Provider outcome uncertain; no automatic retry')
            error.failure_category = failure_category_for(exc)
            raise error from None

    @property
    def drained(self):
        return self._executor.drained.is_set()

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
