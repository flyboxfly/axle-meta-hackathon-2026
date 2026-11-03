"""Durable metadata-only development inbox; not a Telegram webhook.

One PilotInbox owns the memory/database. Transport must authenticate before calling.
No raw messages/media, consent tokens or provider responses are persisted here.
"""
from hashlib import sha256
from secrets import token_urlsafe

from .pilot_memory import PilotMemory


class PilotInbox(PilotMemory):
    def _clear(self, carrier):
        super()._clear(carrier)
        opening = getattr(self, '_opening', None)
        if opening is not None:
            user, chat = next(k for k, value in self._bindings.items() if value == carrier)
            opening.clear(user, chat)
        with self._db:
            self._db.execute('DELETE FROM pilot_media WHERE carrier=?', (carrier,))

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
            # Telegram file references only; image bytes are never stored here.
            self._db.execute('''CREATE TABLE IF NOT EXISTS pilot_media (
                update_id INTEGER PRIMARY KEY, carrier TEXT NOT NULL, file_id TEXT NOT NULL,
                file_unique_id TEXT NOT NULL, mime TEXT NOT NULL, reported_size INTEGER)''')
            # An interrupted paid request has an unknown outcome. Never replay it.
            self._db.execute("UPDATE pilot_updates SET status='uncertain' WHERE status IN ('processing','sending')")
            self._db.execute('''CREATE TABLE IF NOT EXISTS pilot_privacy (
                carrier TEXT NOT NULL,user_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,
                command_id INTEGER NOT NULL,update_id INTEGER NOT NULL,status TEXT NOT NULL,
                PRIMARY KEY(carrier,user_id,chat_id))''')
            self._db.execute('''CREATE TABLE IF NOT EXISTS pilot_message_order (
                carrier TEXT NOT NULL,user_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,PRIMARY KEY(carrier,user_id,chat_id))''')

    def submit(self, user, chat, update_id, action, *, token=None, revision=None, command_id=None,
               message_id=None, media=None) -> bool:
        """True means durably recorded; False means duplicate, without another effect."""
        with self._lock:
            carrier = self._carrier(user, chat)
            if type(update_id) is not int or not 0 <= update_id < 2**63:
                raise ValueError('Invalid update ID')
            if action not in ('evaluate', 'forget', 'screenshot', 'opening'):
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
                    self._db.execute('DELETE FROM pilot_media WHERE carrier=?',(carrier,))
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
            elif action == 'screenshot':
                if revision is not None or command_id is not None or not isinstance(media, dict):
                    raise ValueError('Screenshot needs consent and file references only')
                self._access(user, chat, token)
                file_id, unique = media.get('file_id'), media.get('file_unique_id')
                if (not isinstance(file_id, str) or not 1 <= len(file_id) <= 256
                        or not isinstance(unique, str) or not 1 <= len(unique) <= 128
                        or media.get('mime') not in ('image/png', 'image/jpeg')):
                    raise ValueError('Invalid file reference')
                reported = media.get('reported_size')
                if reported is not None and (type(reported) is not int or reported <= 0):
                    raise ValueError('Invalid reported size')
                generation = sha256(token.encode('ascii')).hexdigest()
            elif action == 'opening':
                if command_id is not None or media is not None:
                    raise ValueError('Opening needs consent and revision only')
                self._access(user, chat, token)
                opening = getattr(self, '_opening', None)
                if opening is None:
                    raise ValueError('Opening workflow unavailable')
                snapshot = opening.get(user, chat)
                if type(revision) is not int or snapshot.revision != revision or not snapshot.confirmed:
                    raise ValueError('Confirmed current revision required')
                generation = sha256(token.encode('ascii')).hexdigest()
            elif token is not None or revision is not None:
                raise ValueError('Forget does not take evaluation arguments')
            if action == 'opening':
                # Shared cross-surface duplicate protection: the same carrier,
                # session generation and confirmed revision reuses its pending
                # evaluation instead of queueing (and later spending) another.
                # New revisions, completed/uncertain rows and rotated sessions
                # are unaffected; explicit re-requests keep existing policy.
                pending = self._db.execute(
                    "SELECT update_id FROM pilot_updates WHERE carrier=? AND action='opening' "
                    'AND revision=? AND generation=? AND status IN '
                    "('queued','processing','sending') LIMIT 1",
                    (carrier, revision, generation)).fetchone()
                if pending is not None:
                    return False
            if self._db.execute('SELECT count(*) FROM pilot_updates').fetchone()[0] >= 10000:
                raise RuntimeError('Inbox capacity reached')
            with self._db:
                self._record_order(carrier,user,chat,message_id)
                self._db.execute('INSERT INTO pilot_updates VALUES (?,?,?,?,?,?,NULL)',
                                 (update_id, carrier, action, revision, generation, 'queued'))
                if action == 'screenshot':
                    self._db.execute('INSERT INTO pilot_media VALUES (?,?,?,?,?,?)',
                        (update_id, carrier, media['file_id'], media['file_unique_id'],
                         media['mime'], media.get('reported_size')))
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

    def claim_screenshot(self, user, chat, update_id, token) -> tuple[str, dict]:
        """Reserve one extraction attempt; caller fetches media only after this claim."""
        with self._lock:
            carrier, _ = self._access(user, chat, token)
            row = self._db.execute('SELECT carrier,action,generation,status FROM pilot_updates '
                                   'WHERE update_id=?', (update_id,)).fetchone()
            media = self._db.execute('SELECT file_id,file_unique_id,mime,reported_size FROM pilot_media '
                                     'WHERE update_id=?', (update_id,)).fetchone()
            if (row is None or media is None or row[0] != carrier or row[1] != 'screenshot'
                    or row[3] != 'queued'
                    or row[2] != sha256(token.encode('ascii')).hexdigest()):
                raise ValueError('Update cannot be claimed')
            claim = token_urlsafe(24)
            with self._db:
                self._db.execute("UPDATE pilot_updates SET status='processing',claim=? WHERE update_id=?",
                                 (claim, update_id))
            return claim, dict(file_id=media[0], file_unique_id=media[1], mime=media[2],
                               reported_size=media[3])

    def claim_opening(self, user, chat, update_id, token) -> tuple[str, int]:
        """Reserve one pricing attempt for a confirmed opening revision."""
        with self._lock:
            carrier, _ = self._access(user, chat, token)
            row = self._db.execute('SELECT carrier,action,revision,generation,status FROM pilot_updates '
                                   'WHERE update_id=?', (update_id,)).fetchone()
            opening = getattr(self, '_opening', None)
            try:
                snapshot = opening.get(user, chat) if opening is not None else None
            except KeyError:
                snapshot = None
            if (row is None or snapshot is None or row[0] != carrier or row[1] != 'opening'
                    or row[4] != 'queued'
                    or row[3] != sha256(token.encode('ascii')).hexdigest()
                    or row[2] != snapshot.revision or not snapshot.confirmed):
                raise ValueError('Update cannot be claimed')
            claim = token_urlsafe(24)
            with self._db:
                self._db.execute("UPDATE pilot_updates SET status='processing',claim=? WHERE update_id=?",
                                 (claim, update_id))
            return claim, row[2]

    def start_delivery(self,user,chat,update_id,claim):
        with self._lock:
            carrier=self._carrier(user,chat)
            with self._db:
                count=self._db.execute("UPDATE pilot_updates SET status='sending' WHERE update_id=? "
                    "AND carrier=? AND claim=? AND status='processing'",(update_id,carrier,claim)).rowcount
                if count != 1:raise ValueError('Stale delivery attempt')

    def finish(self, user, chat, update_id, claim, *, success: bool):
        """Record outcome only. No delivery or authorization follows from this status."""
        with self._lock:
            carrier = self._carrier(user, chat)
            with self._db:
                count = self._db.execute("UPDATE pilot_updates SET status=? WHERE update_id=? AND carrier=? "
                    "AND status IN ('processing','sending') AND claim=?",
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
