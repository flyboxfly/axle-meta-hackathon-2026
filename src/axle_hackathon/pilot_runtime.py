"""Offline single-tick worker and durable attempt caps; no launcher or transports."""
from threading import Event, Lock

from .pilot_telegram import run_evaluation


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
                    with s._db:s._db.execute("UPDATE pilot_updates SET status='uncertain' WHERE update_id=?",(update,))
                    return 'uncertain'
                # run_evaluation claims under the inbox lock before provider work.
                # Shared worker admission prevents another tick from taking this item.
            try:
                run_evaluation(s,self,self.send,user=user,chat=chat,update_id=update)
                return 'completed'
            except Exception:
                with s._lock, s._db:
                    s._db.execute("UPDATE pilot_updates SET status='uncertain' WHERE update_id=? AND status='queued'",(update,))
                return 'uncertain'
        finally:self._busy.release()
