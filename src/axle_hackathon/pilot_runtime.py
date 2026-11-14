"""Offline single-tick worker and durable attempt caps; no launcher or transports."""
from threading import Event, Lock

from .opening_telegram import run_opening, run_screenshot
from .pilot_telegram import run_evaluation
from .pilot_execution import failure_category_for


class PilotWorker:
    def __init__(self, inbox, delegator, send, *, global_limit, carrier_limit):
        if any(type(n) is not int or n <= 0 for n in (global_limit, carrier_limit)):
            raise ValueError('Explicit positive attempt caps required')
        self.inbox, self.delegator, self.send = inbox, delegator, send
        self.global_limit, self.carrier_limit = global_limit, carrier_limit
        self._closed = Event()
        with inbox._lock, inbox._db:
            if inbox._closed:raise RuntimeError('Inbox closed')
            if not hasattr(inbox, '_worker_busy'):inbox._worker_busy = Lock()
            self._busy = inbox._worker_busy
            inbox._db.execute('CREATE TABLE IF NOT EXISTS pilot_budget '
                              '(carrier TEXT PRIMARY KEY, attempts INTEGER NOT NULL)')

    def close(self):
        # Does not cancel an already claimed attempt or its external I/O.
        self._closed.set()

    def _evaluate(self, user, chat, token, revision):
        s = self.inbox
        with s._lock:
            carrier, _ = s._access(user, chat, token)
            snapshot = s.get(user, chat, token)
            if snapshot.revision != revision or not snapshot.confirmed:
                raise ValueError('Current confirmation required')
            with s._db:
                total = s._db.execute('SELECT COALESCE(SUM(attempts),0) FROM pilot_budget').fetchone()[0]
                row = s._db.execute('SELECT attempts FROM pilot_budget WHERE carrier=?',(carrier,)).fetchone()
                used = row[0] if row else 0
                if total >= self.global_limit or used >= self.carrier_limit:
                    raise RuntimeError('Attempt budget exhausted')
                s._db.execute('INSERT OR REPLACE INTO pilot_budget VALUES (?,?)',(carrier,used+1))
        # Reservation survives all failures, withdrawal and restart. No refund/retry.
        return self.delegator.evaluate(user, chat, token, revision)

    def evaluate(self, *args):
        """Internal adapter used only after run_evaluation's durable task claim."""
        return self._evaluate(*args)

    def tick(self):
        """One bounded scan and at most one model attempt; host supplies scheduling."""
        if not self._busy.acquire(blocking=False):return 'busy'
        try:
            s = self.inbox
            with s._lock:
                if self._closed.is_set() or s._closed:return 'closed'
                s.purge_expired()
                # Privacy is serviced before evaluation, including when budgets are spent.
                rows = s._db.execute("SELECT user_id,chat_id,update_id FROM pilot_privacy WHERE status!='completed'").fetchall()
                for user,chat,update in rows:
                    s.process_forget(user,chat,update)
                row = s._db.execute("SELECT update_id,carrier FROM pilot_updates WHERE action='evaluate' "
                                    "AND status='queued' ORDER BY rowid LIMIT 1").fetchone()
                if row is None:return 'idle'
                update,carrier = row
                user,chat = next(k for k,v in s._bindings.items() if v == carrier)
                access = s._active.get(carrier)
                if access is None:
                    with s._db:
                        s._db.execute("UPDATE pilot_updates SET status='uncertain' WHERE update_id=?",(update,))
                        s._db.execute("INSERT OR REPLACE INTO pilot_failure_categories VALUES (?,?)",(update,'consent_unavailable'))
                    return 'uncertain'
                # run_evaluation claims under the inbox lock before provider work.
                # Shared worker admission prevents another tick from taking this item.
            try:
                run_evaluation(s,self,self.send,user=user,chat=chat,update_id=update)
                return 'completed'
            except Exception:
                with s._lock, s._db:
                    changed=s._db.execute("UPDATE pilot_updates SET status='uncertain' WHERE update_id=? AND status='queued'",(update,)).rowcount
                    if changed:s._db.execute("INSERT OR REPLACE INTO pilot_failure_categories VALUES (?,?)",(update,'unknown'))
                return 'uncertain'
        finally:self._busy.release()


class OpeningWorker:
    """Opening worker with durable provider caps and an opt-in Warp workflow."""
    def __init__(self, inbox, delegator, send, *, global_limit, carrier_limit, warp=False):
        if any(type(n) is not int or n <= 0 for n in (global_limit, carrier_limit)):
            raise ValueError('Explicit positive attempt caps required')
        self.inbox, self.delegator, self.send = inbox, delegator, send
        self.global_limit, self.carrier_limit = global_limit, carrier_limit
        if warp and (global_limit, carrier_limit) != (3, 3):
            raise ValueError('Warp requires three cumulative provider attempts')
        self.warp = warp
        self._closed = Event()
        with inbox._lock, inbox._db:
            if inbox._closed:raise RuntimeError('Inbox closed')
            if not hasattr(inbox, '_opening_busy'):inbox._opening_busy = Lock()
            self._busy = inbox._opening_busy
            inbox._db.execute('CREATE TABLE IF NOT EXISTS pilot_budget '
                              '(carrier TEXT PRIMARY KEY, attempts INTEGER NOT NULL)')

    def close(self):
        # Does not cancel an already claimed attempt or its external I/O.
        self._closed.set()

    def _remaining(self, carrier):
        db = self.inbox._db
        total = db.execute('SELECT COALESCE(SUM(attempts),0) FROM pilot_budget').fetchone()[0]
        row = db.execute('SELECT attempts FROM pilot_budget WHERE carrier=?', (carrier,)).fetchone()
        return min(self.global_limit - total, self.carrier_limit - (row[0] if row else 0))

    def screenshot_budget_exhausted(self, user, chat, token):
        with self.inbox._lock:
            carrier, _ = self.inbox._access(user, chat, token)
            return self._remaining(carrier) <= 0

    def _reserve(self, user, chat, token):
        s = self.inbox
        with s._lock, s._db:
            carrier, _ = s._access(user, chat, token)
            if self._remaining(carrier) <= 0:
                raise RuntimeError('Attempt budget exhausted')
            s._db.execute('INSERT INTO pilot_budget VALUES (?,1) '
                          'ON CONFLICT(carrier) DO UPDATE SET attempts=attempts+1', (carrier,))

    def screenshot(self, user, chat, token, file_id, mime, *, expected_revision):
        """Process one durable screenshot claim under the configured pilot policy."""
        if not self.warp:
            self._reserve(user, chat, token)
            return self.delegator.extract(user, chat, token, file_id, mime,
                                          expected_revision=expected_revision)

        s = self.inbox

        def check_current():
            if self._closed.is_set():
                raise RuntimeError('Worker closed')
            carrier, _ = s._access(user, chat, token)
            try:
                revision = s._opening.get(user, chat).revision
            except KeyError:
                revision = 0
            if revision != expected_revision:
                raise ValueError('Stale revision')
            return carrier

        def admit():
            with s._lock:
                check_current()
                self._reserve(user, chat, token)

        for attempt in range(3):
            with s._lock:
                if self._remaining(check_current()) <= 0:
                    raise RuntimeError('Attempt budget exhausted')
            try:
                return self.delegator.extract(user, chat, token, file_id, mime,
                    expected_revision=expected_revision, admit=admit, retry=attempt > 0)
            except Exception as exc:
                category = failure_category_for(exc)
                retryable = category == 'provider_unavailable' or (
                    category.startswith('extraction_') and category != 'extraction_filtered')
                with s._lock:
                    if not retryable or attempt == 2 or self._remaining(check_current()) <= 0:
                        raise

    def opening(self, user, chat, token, revision):
        """Price a confirmed Warp draft locally; other pilots retain model selection."""
        if self.warp:
            with self.inbox._lock:
                self.inbox._access(user, chat, token)
                kind, result = self.inbox._opening.decide(user, chat, revision)
                return {'kind': kind, 'result': result}
        self._reserve(user, chat, token)
        return self.delegator.select_pricing(user, chat, token, revision)

    def tick(self):
        """Process one queued update; the durable caps bound provider work."""
        if not self._busy.acquire(blocking=False):return 'busy'
        try:
            s = self.inbox
            with s._lock:
                if self._closed.is_set() or s._closed:return 'closed'
                s.purge_expired()
                # Privacy is serviced before paid work, including when budgets are spent.
                rows = s._db.execute("SELECT user_id,chat_id,update_id FROM pilot_privacy WHERE status!='completed'").fetchall()
                for user,chat,update in rows:
                    s.process_forget(user,chat,update)
                row = s._db.execute("SELECT update_id,carrier,action FROM pilot_updates "
                                    "WHERE action IN ('screenshot','opening') "
                                    "AND status='queued' ORDER BY rowid LIMIT 1").fetchone()
                if row is None:return 'idle'
                update,carrier,action = row
                user,chat = next(k for k,v in s._bindings.items() if v == carrier)
                access = s._active.get(carrier)
                if access is None:
                    with s._db:
                        s._db.execute("UPDATE pilot_updates SET status='uncertain' WHERE update_id=?",(update,))
                        s._db.execute("INSERT OR REPLACE INTO pilot_failure_categories VALUES (?,?)",(update,'consent_unavailable'))
                    return 'uncertain'
                # run_screenshot/run_opening claim under the inbox lock before provider work.
                # Shared worker admission prevents another tick from taking this item.
            try:
                if action == 'screenshot':
                    run_screenshot(s,self,self.send,user=user,chat=chat,update_id=update)
                else:
                    run_opening(s,self,self.send,user=user,chat=chat,update_id=update)
                return 'completed'
            except Exception:
                with s._lock, s._db:
                    changed=s._db.execute("UPDATE pilot_updates SET status='uncertain' WHERE update_id=? AND status='queued'",(update,)).rowcount
                    if changed:s._db.execute("INSERT OR REPLACE INTO pilot_failure_categories VALUES (?,?)",(update,'unknown'))
                return 'uncertain'
        finally:self._busy.release()
