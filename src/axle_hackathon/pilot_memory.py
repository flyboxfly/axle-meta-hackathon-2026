"""Offline consent/storage boundary. No Telegram authentication or provider approval.

Only the trusted adapter may supply identity, consent actions and confirmed facts.
None of this module's methods are model tools. One owning process per database.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import compare_digest, token_urlsafe
import sqlite3
from threading import RLock
from typing import Callable, Literal

from pydantic import Field, ValidationError

from .pilot import Frozen, Opportunity, PilotSessions, Profile, Snapshot


def _token_matches(expected: str, supplied: str) -> bool:
    return (isinstance(supplied, str) and supplied.isascii()
            and len(supplied) == len(expected) and compare_digest(expected, supplied))


class MemoryPolicy(Frozen):
    # This supplied notice must be reconciled with actual providers before release.
    version: str = Field(min_length=1, max_length=80)
    processing_notice: str = Field(min_length=1, max_length=4000)
    session_seconds: int = Field(default=3600, gt=0, le=86400)
    profile_seconds: int = Field(default=2592000, gt=0, le=2592000)


@dataclass(frozen=True)
class Disclosure:
    token: str
    text: str
    expires_at: datetime


@dataclass(frozen=True)
class Access:
    token: str
    choice: Literal['session_only', 'remember_profile']
    consented_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class SavedProfile:
    version: str
    profile: Profile
    saved_at: datetime
    expires_at: datetime
    disclosure_version: str
    source_revision: int
    # Historical confirmation, never authorization for a new opportunity.
    source_confirmed_at: datetime
    consented_at: datetime


class PilotMemory:
    """Single-process facade: authorize -> consent -> scoped session/storage work.

    Session consent is volatile. Restart requires disclosure and consent again.
    Saved profiles are explicit drafts on reload, with optimistic version checks.
    Expiry is checked on access; the host must also schedule purge_expired().
    SQLite deletion does not promise erasure from storage media or external backups.
    """
    def __init__(self, path: str | Path, bindings: dict[tuple[int, int], str],
                 policy: MemoryPolicy, *, clock: Callable[[], datetime] | None = None):
        for (user, chat), carrier in bindings.items():
            if type(user) is not int or type(chat) is not int or user <= 0 or chat <= 0:
                raise ValueError('Positive numeric private-chat bindings required')
            if not isinstance(carrier, str) or not carrier:
                raise ValueError('Carrier binding required')
        self._bindings = dict(bindings)
        self._policy = policy
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._closed = False
        self._pending_deletions: set[str] = set()
        self._sessions = PilotSessions(bindings)
        self._notices: dict[str, Disclosure] = {}
        self._active: dict[str, Access] = {}
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute('PRAGMA journal_mode=DELETE')
        self._db.execute('PRAGMA secure_delete=ON')
        self._db.execute('''CREATE TABLE IF NOT EXISTS pilot_profiles (
            carrier TEXT PRIMARY KEY, version TEXT NOT NULL, profile TEXT NOT NULL,
            saved_at TEXT NOT NULL, expires_at REAL NOT NULL,
            disclosure_version TEXT NOT NULL, source_revision INTEGER NOT NULL,
            source_confirmed_at TEXT NOT NULL, consented_at TEXT NOT NULL)''')
        self._db.commit()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._active.clear()
            self._notices.clear()
            self._sessions = PilotSessions(self._bindings)
            self._db.close()

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('Timezone-aware clock required')
        return now.astimezone(timezone.utc)

    def _carrier(self, user: int, chat: int) -> str:
        # bool and floats must not alias numeric IDs in Python dict lookup.
        if type(user) is not int or type(chat) is not int or (user, chat) not in self._bindings:
            raise PermissionError('Unapproved private chat')
        if self._closed:
            raise RuntimeError('Pilot memory is closed')
        return self._bindings[(user, chat)]

    def _clear(self, carrier: str):
        self._active.pop(carrier, None)
        self._notices.pop(carrier, None)
        # All owner-approved bindings for a carrier share one carrier session.
        user, chat = next(k for k, value in self._bindings.items() if value == carrier)
        self._sessions.clear(user, chat)

    def _access(self, user: int, chat: int, token: str) -> tuple[str, Access]:
        carrier = self._carrier(user, chat)
        access = self._active.get(carrier)
        if access is not None and access.expires_at <= self._now():
            self._clear(carrier)
            access = None
        if access is None or not _token_matches(access.token, token):
            raise PermissionError('Current consent required')
        return carrier, access

    def disclosure(self, user: int, chat: int) -> Disclosure:
        with self._lock:
            carrier = self._carrier(user, chat)
            text = (f'{self._policy.processing_notice}\n'
                    f'Disclosure version: {self._policy.version}. '
                    f'Session-only: access expires {self._policy.session_seconds} seconds from consent. '
                    'Active state is in process memory and clears on expiry access/maintenance, '
                    'restart or forget. '
                    f'Remember profile: separately save a reviewed profile for at most '
                    f'{self._policy.profile_seconds} seconds from each explicit save. '
                    'Opportunities, images, messages and results are not stored in this profile database. '
                    'Choosing session-only removes any saved profile. Forget withdraws consent and '
                    'removes active state and the saved database record. Expired profiles are unavailable; '
                    'physical cleanup runs on access or scheduled maintenance. Database deletion does not '
                    'erase provider histories, infrastructure logs, backups or storage-media remnants. '
                    'No secondary research, training, sharing or public-evidence permission is granted.')
            notice = Disclosure(token_urlsafe(24), text, self._now() + timedelta(minutes=5))
            self._notices[carrier] = notice
            return notice

    def consent(self, user: int, chat: int, notice_token: str,
                choice: Literal['session_only', 'remember_profile']) -> Access:
        with self._lock:
            carrier = self._carrier(user, chat)
            notice = self._notices.get(carrier)
            if choice not in ('session_only', 'remember_profile'):
                raise ValueError('Explicit memory choice required')
            if (notice is None or notice.expires_at <= self._now()
                    or not _token_matches(notice.token, notice_token)):
                raise PermissionError('Current disclosure acknowledgement required')
            self._clear(carrier)
            if choice == 'session_only' or carrier in self._pending_deletions:
                self._delete_profile(carrier)
            now = self._now()
            access = Access(token_urlsafe(24), choice, now,
                            now + timedelta(seconds=self._policy.session_seconds))
            self._active[carrier] = access
            return access

    def put(self, user: int, chat: int, token: str, profile: Profile, opportunity: Opportunity,
            *, expected_revision: int) -> Snapshot:
        with self._lock:
            self._access(user, chat, token)
            return self._sessions.put(user, chat, profile, opportunity,
                                      expected_revision=expected_revision)

    def get(self, user: int, chat: int, token: str) -> Snapshot:
        with self._lock:
            self._access(user, chat, token)
            return self._sessions.get(user, chat)

    def confirm(self, user: int, chat: int, token: str, revision: int) -> Snapshot:
        with self._lock:
            self._access(user, chat, token)
            return self._sessions.confirm(user, chat, revision)

    def evaluate(self, user: int, chat: int, token: str, revision: int) -> dict:
        with self._lock:
            self._access(user, chat, token)
            return self._sessions.evaluate(user, chat, revision)

    def _expire_profile(self, carrier: str):
        with self._db:
            self._db.execute('DELETE FROM pilot_profiles WHERE carrier=? AND expires_at<=?',
                             (carrier, self._now().timestamp()))

    def load_profile(self, user: int, chat: int, token: str) -> SavedProfile | None:
        with self._lock:
            carrier, access = self._access(user, chat, token)
            if access.choice != 'remember_profile':
                raise PermissionError('Profile storage consent required')
            self._expire_profile(carrier)
            row = self._db.execute('''SELECT version,profile,saved_at,expires_at,
                disclosure_version,source_revision,source_confirmed_at,consented_at
                FROM pilot_profiles WHERE carrier=?''', (carrier,)).fetchone()
            if row is None:
                return None
            try:
                return SavedProfile(row[0], Profile.model_validate_json(row[1]),
                    datetime.fromisoformat(row[2]), datetime.fromtimestamp(row[3], timezone.utc),
                    row[4], row[5], datetime.fromisoformat(row[6]), datetime.fromisoformat(row[7]))
            except (ValidationError, ValueError, TypeError):
                raise ValueError('Saved profile cannot be loaded') from None

    def save_profile(self, user: int, chat: int, token: str, revision: int,
                     *, expected_version: str | None) -> SavedProfile:
        with self._lock:
            carrier, access = self._access(user, chat, token)
            if access.choice != 'remember_profile':
                raise PermissionError('Profile storage consent required')
            snapshot = self._sessions.get(user, chat)
            if snapshot.revision != revision or not snapshot.confirmed or snapshot.confirmed_at is None:
                raise ValueError('Confirm the current snapshot before saving')
            now = self._now()
            expires = now + timedelta(seconds=self._policy.profile_seconds)
            version = token_urlsafe(24)
            # BEGIN IMMEDIATE plus compare-and-write keeps the replacement atomic.
            with self._db:
                self._db.execute('BEGIN IMMEDIATE')
                self._db.execute('DELETE FROM pilot_profiles WHERE carrier=? AND expires_at<=?',
                                 (carrier, now.timestamp()))
                row = self._db.execute('SELECT version FROM pilot_profiles WHERE carrier=?',
                                       (carrier,)).fetchone()
                if expected_version != (row[0] if row else None):
                    raise ValueError('Stale saved profile version')
                self._db.execute('''INSERT OR REPLACE INTO pilot_profiles
                    VALUES (?,?,?,?,?,?,?,?,?)''', (carrier, version, snapshot.profile.model_dump_json(),
                    now.isoformat(), expires.timestamp(), self._policy.version,
                    snapshot.revision, snapshot.confirmed_at.isoformat(), access.consented_at.isoformat()))
            return SavedProfile(version, snapshot.profile, now, expires, self._policy.version,
                                snapshot.revision, snapshot.confirmed_at, access.consented_at)

    def forget(self, user: int, chat: int):
        """Authorized carrier can withdraw without an active consent/session token."""
        with self._lock:
            carrier = self._carrier(user, chat)
            self._clear(carrier)
            self._delete_profile(carrier)

    def _delete_profile(self, carrier: str):
        # Remains latched if the transaction fails. Host recovery must handle restart.
        self._pending_deletions.add(carrier)
        with self._db:
            self._db.execute('DELETE FROM pilot_profiles WHERE carrier=?', (carrier,))
        self._pending_deletions.discard(carrier)

    def purge_expired(self):
        """Trusted host maintenance; no user/model parameters or returned private data."""
        with self._lock:
            if self._closed:
                raise RuntimeError('Pilot memory is closed')
            now = self._now()
            for carrier, access in tuple(self._active.items()):
                if access.expires_at <= now:
                    self._clear(carrier)
            for carrier, notice in tuple(self._notices.items()):
                if notice.expires_at <= now:
                    self._notices.pop(carrier, None)
            with self._db:
                self._db.execute('DELETE FROM pilot_profiles WHERE expires_at<=?', (now.timestamp(),))
