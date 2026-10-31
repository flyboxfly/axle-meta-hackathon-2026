"""Durable metadata-only development inbox; not a Telegram webhook.

One PilotInbox owns the memory/database. Transport must authenticate before calling.
No raw messages/media, consent tokens or provider responses are persisted here.
"""
from hashlib import sha256
from secrets import token_urlsafe

from .pilot_memory import PilotMemory


class PilotInbox(PilotMemory):
    def stale_message(self,user,chat,message_id):
        with self._lock:
            carrier=self._carrier(user,chat)
            if type(message_id) is not int or not 0 < message_id < 2**63:
                raise ValueError('Positive message ID required')
            row=self._db.execute('SELECT message_id FROM pilot_message_order '
                'WHERE carrier=? AND user_id=? AND chat_id=?',(carrier,user,chat)).fetchone()
            return row is not None and message_id <= row[0]

    def _record_order(self,carrier,user,chat,message_id):
        if message_id is not None:
            self._db.execute('INSERT OR REPLACE INTO pilot_message_order VALUES (?,?,?,?)',
                             (carrier,user,chat,message_id))

    def begin_flow(self, user, chat, update_id, *, message_id=None):
        """Durable at-most-one attempt for a volatile conversation transition."""
        with self._lock:
            carrier = self._carrier(user, chat)
            if self.duplicate_update(user,chat,update_id,'flow'):
                return None
            if message_id is not None and self.stale_message(user,chat,message_id):
                return None
            if self._db.execute('SELECT count(*) FROM pilot_updates').fetchone()[0] >= 10000:
                raise RuntimeError('Inbox capacity reached')
            claim = token_urlsafe(24)
            with self._db:
                self._record_order(carrier,user,chat,message_id)
                self._db.execute('INSERT INTO pilot_updates VALUES (?,?,?,?,?,?,?)',
                    (update_id,carrier,'flow',None,None,'processing',claim))
            return claim

    def duplicate_update(self, user, chat, update_id, action, *, command_id=None) -> bool:
        with self._lock:
            carrier = self._carrier(user, chat)
            if type(update_id) is not int or not 0 <= update_id < 2**63:
                raise ValueError('Invalid update ID')
            row = self._db.execute('SELECT carrier,action FROM pilot_updates WHERE update_id=?',
                                   (update_id,)).fetchone()
            if row and row != (carrier, action):
                raise PermissionError('Update scope mismatch')
            recorded = self._db.execute('SELECT carrier,user_id,chat_id FROM pilot_privacy WHERE update_id=?',
                                        (update_id,)).fetchone()
            if recorded:
                if action != 'forget' or recorded != (carrier,user,chat):
                    raise PermissionError('Update scope mismatch')
                return True
            if action == 'forget':
                command_id = update_id if command_id is None else command_id
                if type(command_id) is not int or command_id <= 0:
                    raise ValueError('Positive privacy command ID required')
                old = self._db.execute('SELECT command_id FROM pilot_privacy WHERE carrier=? AND user_id=? AND chat_id=?',
                                       (carrier,user,chat)).fetchone()
                if old and command_id <= old[0]:
                    return True
            return row is not None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with self._db:
            self._db.execute('''CREATE TABLE IF NOT EXISTS pilot_updates (
                update_id INTEGER PRIMARY KEY, carrier TEXT NOT NULL, action TEXT NOT NULL,
                revision INTEGER, generation TEXT, status TEXT NOT NULL, claim TEXT)''')
            # An interrupted paid request has an unknown outcome. Never replay it.
            self._db.execute("UPDATE pilot_updates SET status='uncertain' WHERE status='processing'")
            self._db.execute('''CREATE TABLE IF NOT EXISTS pilot_privacy (
                carrier TEXT NOT NULL,user_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,
                command_id INTEGER NOT NULL,update_id INTEGER NOT NULL,status TEXT NOT NULL,
                PRIMARY KEY(carrier,user_id,chat_id))''')
            self._db.execute('''CREATE TABLE IF NOT EXISTS pilot_message_order (
                carrier TEXT NOT NULL,user_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,PRIMARY KEY(carrier,user_id,chat_id))''')

    def submit(self, user, chat, update_id, action, *, token=None, revision=None, command_id=None,
               message_id=None) -> bool:
        """True means durably recorded; False means duplicate, without another effect."""
        with self._lock:
            carrier = self._carrier(user, chat)
            if type(update_id) is not int or not 0 <= update_id < 2**63:
                raise ValueError('Invalid update ID')
            if action not in ('evaluate', 'forget'):
                raise ValueError('Unsupported inbox action')
            if message_id is not None and self.stale_message(user,chat,message_id):
                return False
            row = self._db.execute('SELECT carrier,action FROM pilot_updates WHERE update_id=?',
                                   (update_id,)).fetchone()
            if row:
                if row != (carrier, action):
                    raise PermissionError('Update scope mismatch')
                return False
            if action == 'forget':
                if token is not None or revision is not None:
                    raise ValueError('Forget does not take evaluation arguments')
                if self.duplicate_update(user,chat,update_id,action,command_id=command_id):
                    return False
                command_id = update_id if command_id is None else command_id
                # Stop active processing even if storage cannot accept the intent.
                self._clear(carrier)
                self._pending_deletions.add(carrier)
                with self._db:
                    self._record_order(carrier,user,chat,message_id)
                    self._db.execute('INSERT OR REPLACE INTO pilot_privacy VALUES (?,?,?,?,?,?)',
                                     (carrier,user,chat,command_id,update_id,'queued'))
                    self._db.execute('INSERT OR IGNORE INTO pilot_deletions VALUES (?)',(carrier,))
                return True
            generation = None
            if self.duplicate_update(user,chat,update_id,action):
                return False
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
                self._record_order(carrier,user,chat,message_id)
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
            privacy = self._db.execute('SELECT update_id,status FROM pilot_privacy '
                'WHERE carrier=? AND user_id=? AND chat_id=?',(carrier,user,chat)).fetchone()
            if privacy and privacy[0] == update_id:
                if privacy[1] != 'completed':
                    if self._db.execute('SELECT 1 FROM pilot_deletions WHERE carrier=?',(carrier,)).fetchone():
                        self.forget(user,chat)
                    with self._db:
                        self._db.execute("UPDATE pilot_privacy SET status='completed' "
                            'WHERE carrier=? AND user_id=? AND chat_id=?',(carrier,user,chat))
                return
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
