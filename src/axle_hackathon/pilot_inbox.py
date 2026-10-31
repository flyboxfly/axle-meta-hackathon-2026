"""Durable metadata-only development inbox; not a Telegram webhook.

One PilotInbox owns the memory/database. Transport must authenticate before calling.
No raw messages/media, consent tokens or provider responses are persisted here.
"""
from hashlib import sha256
from secrets import token_urlsafe

from .pilot_memory import PilotMemory


class PilotInbox(PilotMemory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with self._db:
            self._db.execute('''CREATE TABLE IF NOT EXISTS pilot_updates (
                update_id INTEGER PRIMARY KEY, carrier TEXT NOT NULL, action TEXT NOT NULL,
                revision INTEGER, generation TEXT, status TEXT NOT NULL, claim TEXT)''')
            # An interrupted paid request has an unknown outcome. Never replay it.
            self._db.execute("UPDATE pilot_updates SET status='uncertain' WHERE status='processing'")

    def submit(self, user, chat, update_id, action, *, token=None, revision=None) -> bool:
        """True means durably recorded; False means duplicate, without another effect."""
        with self._lock:
            carrier = self._carrier(user, chat)
            if type(update_id) is not int or not 0 <= update_id < 2**63:
                raise ValueError('Invalid update ID')
            if action not in ('evaluate', 'forget'):
                raise ValueError('Unsupported inbox action')
            row = self._db.execute('SELECT carrier,action FROM pilot_updates WHERE update_id=?',
                                   (update_id,)).fetchone()
            if row:
                if row != (carrier, action):
                    raise PermissionError('Update scope mismatch')
                return False
            generation = None
            if action == 'evaluate':
                self._access(user, chat, token)
                snapshot = self._sessions.get(user, chat)
                if type(revision) is not int or snapshot.revision != revision or not snapshot.confirmed:
                    raise ValueError('Confirmed current revision required')
                generation = sha256(token.encode('ascii')).hexdigest()
            elif token is not None or revision is not None:
                raise ValueError('Forget does not take evaluation arguments')
            if self._db.execute('SELECT count(*) FROM pilot_updates').fetchone()[0] >= 10000:
                raise RuntimeError('Inbox capacity reached')
            with self._db:
                self._db.execute('INSERT INTO pilot_updates VALUES (?,?,?,?,?,?,NULL)',
                                 (update_id, carrier, action, revision, generation, 'queued'))
                if action == 'forget':
                    self._db.execute('INSERT OR IGNORE INTO pilot_deletions VALUES (?)', (carrier,))
            if action == 'forget':
                self._clear(carrier)
            return True

    def claim_evaluation(self, user, chat, update_id, token) -> tuple[str, int]:
        """Reserve one attempt BEFORE model work; caller must not retry after uncertainty."""
        with self._lock:
            carrier, _ = self._access(user, chat, token)
            row = self._db.execute('SELECT carrier,action,revision,generation,status FROM pilot_updates '
                                   'WHERE update_id=?', (update_id,)).fetchone()
            snapshot = self._sessions.get(user, chat)
            if (row is None or row[0] != carrier or row[1] != 'evaluate' or row[4] != 'queued'
                    or row[3] != sha256(token.encode('ascii')).hexdigest()
                    or row[2] != snapshot.revision or not snapshot.confirmed):
                raise ValueError('Update cannot be claimed')
            claim = token_urlsafe(24)
            with self._db:
                self._db.execute("UPDATE pilot_updates SET status='processing',claim=? WHERE update_id=?",
                                 (claim, update_id))
            return claim, row[2]

    def finish(self, user, chat, update_id, claim, *, success: bool):
        """Record outcome only. No delivery or authorization follows from this status."""
        with self._lock:
            carrier = self._carrier(user, chat)
            with self._db:
                count = self._db.execute("UPDATE pilot_updates SET status=? WHERE update_id=? AND carrier=? "
                    "AND status='processing' AND claim=?",
                    ('completed' if success else 'uncertain', update_id, carrier, claim)).rowcount
                if count != 1:
                    raise ValueError('Stale task completion')

    def process_forget(self, user, chat, update_id):
        with self._lock:
            carrier = self._carrier(user, chat)
            row = self._db.execute('SELECT carrier,action,status FROM pilot_updates WHERE update_id=?',
                                   (update_id,)).fetchone()
            if row is None or row[:2] != (carrier, 'forget'):
                raise PermissionError('Update scope mismatch')
            if row[2] == 'completed':
                return
            if self._db.execute('SELECT 1 FROM pilot_deletions WHERE carrier=?', (carrier,)).fetchone():
                self.forget(user, chat)
            with self._db:
                self._db.execute("UPDATE pilot_updates SET status='completed' WHERE update_id=?", (update_id,))
