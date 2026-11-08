"""Consent-gated single-truck profile storage on the existing private SQLite owner.

Only reviewed profile facts are persisted. No screenshots, trip facts, results,
location or model responses. Identity is supplied by the trusted chat binding.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from .opening_workflow import OpeningProfile
from .pilot_memory import _token_matches


@dataclass(frozen=True)
class SavedOpeningProfile:
    version: str
    profile: OpeningProfile
    saved_at: datetime
    expires_at: datetime
    disclosure_version: str


class OpeningProfileStore:
    def __init__(self, inbox):
        self.inbox = inbox

    def load(self, user, chat, token):
        s = self.inbox
        with s._lock:
            carrier, access = s._access(user, chat, token)
            if access.choice != 'remember_profile':
                raise PermissionError('Profile storage consent required')
            if (carrier in s._pending_deletions or s._db.execute(
                    'SELECT 1 FROM pilot_deletions WHERE carrier=?', (carrier,)).fetchone()):
                raise PermissionError('Profile deletion pending')
            with s._db:
                s._db.execute('DELETE FROM opening_profiles WHERE carrier=? AND expires_at<=?',
                              (carrier, s._now().timestamp()))
            row = s._db.execute('SELECT version,profile,saved_at,expires_at,disclosure_version '
                                'FROM opening_profiles WHERE carrier=?', (carrier,)).fetchone()
            if row is None:
                return None
            try:
                return SavedOpeningProfile(row[0], OpeningProfile.model_validate_json(row[1]),
                    datetime.fromisoformat(row[2]), datetime.fromtimestamp(row[3], timezone.utc), row[4])
            except (ValueError, TypeError):
                raise ValueError('Saved truck profile cannot be loaded') from None

    def save_reviewed(self, user, chat, token, nonce, *, expected_version):
        """Save only the exact current chat review, with durable compare-and-write."""
        s = self.inbox
        with s._lock:
            carrier, access = s._access(user, chat, token)
            if access.choice != 'remember_profile':
                raise PermissionError('Choose remember before saving a profile')
            flow = s._conversation_states.get(carrier)
            if (flow is None or flow['step'] != 'profile_review'
                    or not _token_matches(flow['nonce'], nonce)
                    or flow.get('profile_values') is None
                    or flow.get('profile_version_at_review') != s._opening.profile_version(user, chat)):
                raise ValueError('Review the current truck profile before saving')
            profile = OpeningProfile.model_validate(flow['profile_values'].model_dump())
            now = s._now()
            expires = now + timedelta(seconds=s._policy.profile_seconds)
            version = token_urlsafe(24)
            with s._db:
                s._db.execute('BEGIN IMMEDIATE')
                if (carrier in s._pending_deletions or s._db.execute(
                        'SELECT 1 FROM pilot_deletions WHERE carrier=?', (carrier,)).fetchone()):
                    raise PermissionError('Profile deletion pending')
                s._db.execute('DELETE FROM opening_profiles WHERE carrier=? AND expires_at<=?',
                              (carrier, now.timestamp()))
                row = s._db.execute('SELECT version FROM opening_profiles WHERE carrier=?',
                                    (carrier,)).fetchone()
                if expected_version != (row[0] if row else None):
                    raise ValueError('Stale saved truck profile version')
                s._db.execute('INSERT OR REPLACE INTO opening_profiles VALUES (?,?,?,?,?,?,?)',
                    (carrier, version, profile.model_dump_json(), now.isoformat(), expires.timestamp(),
                     s._policy.version, access.consented_at.isoformat()))
            return SavedOpeningProfile(version, profile, now, expires, s._policy.version)
