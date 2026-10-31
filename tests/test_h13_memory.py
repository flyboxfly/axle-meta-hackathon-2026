"""Offline storage/consent tests with invented profiles in temporary databases."""
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from axle_hackathon.pilot_memory import MemoryPolicy, PilotMemory
from test_h13_pilot import offer, profile


class Clock:
    now = datetime(2026, 10, 31, 18, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / 'profiles.sqlite3'
    clock = Clock()
    policy = MemoryPolicy(version='offline-test-v1', processing_notice='Synthetic offline tests only.',
                          session_seconds=60, profile_seconds=120)
    store = PilotMemory(path, {(1, 1): 'a', (2, 2): 'b'}, policy, clock=clock)
    yield store, path, clock, policy
    store.close()


def consent(store, user=1, choice='remember_profile'):
    notice = store.disclosure(user, user)
    return store.consent(user, user, notice.token, choice)


def confirmed(store, access, user=1):
    s = store.put(user, user, access.token, profile(), offer(), expected_revision=0)
    return store.confirm(user, user, access.token, s.revision)


def save(store, access, user=1):
    s = confirmed(store, access, user)
    return store.save_profile(user, user, access.token, s.revision, expected_version=None)


def rows(path):
    with sqlite3.connect(path) as db:
        return db.execute('SELECT * FROM pilot_profiles').fetchall()


def test_no_implicit_consent_or_storage(setup):
    store, path, _, _ = setup
    for call in [lambda: store.put(1, 1, '', profile(), offer(), expected_revision=0),
                 lambda: store.get(1, 1, ''), lambda: store.confirm(1, 1, '', 1),
                 lambda: store.evaluate(1, 1, '', 1), lambda: store.load_profile(1, 1, ''),
                 lambda: store.save_profile(1, 1, '', 1, expected_version=None)]:
        with pytest.raises(PermissionError):
            call()
    assert rows(path) == []


def test_session_only_never_persists_and_can_evaluate(setup):
    store, path, _, _ = setup
    access = consent(store, choice='session_only')
    confirmed(store, access)
    assert store.evaluate(1, 1, access.token, 1)['gap'] == '60.00'
    with pytest.raises(PermissionError):
        store.save_profile(1, 1, access.token, 1, expected_version=None)
    with pytest.raises(PermissionError):
        store.load_profile(1, 1, access.token)
    assert rows(path) == []


def test_only_explicit_confirmed_profile_save_is_durable(setup):
    store, path, _, policy = setup
    access = consent(store)
    store.put(1, 1, access.token, profile(), offer(scope='private opportunity marker'), expected_revision=0)
    with pytest.raises(ValueError):
        store.save_profile(1, 1, access.token, 1, expected_version=None)
    assert rows(path) == []
    store.confirm(1, 1, access.token, 1)
    assert rows(path) == []
    saved = store.save_profile(1, 1, access.token, 1, expected_version=None)
    assert saved == store.load_profile(1, 1, access.token)
    assert saved.disclosure_version == policy.version
    assert saved.consented_at == access.consented_at
    assert saved.source_revision == 1
    assert 'private opportunity marker' not in str(rows(path))
    assert len(rows(path)) == 1


def test_restart_requires_new_consent_and_loaded_profile_is_not_a_trip_confirmation(setup):
    store, path, clock, policy = setup
    access = consent(store)
    saved = save(store, access)
    store.close()
    other = PilotMemory(path, {(1, 1): 'a'}, policy, clock=clock)
    try:
        with pytest.raises(PermissionError):
            other.load_profile(1, 1, access.token)
        new = consent(other)
        restored = other.load_profile(1, 1, new.token)
        assert restored.profile == saved.profile
        with pytest.raises(KeyError):
            other.get(1, 1, new.token)
        s = other.put(1, 1, new.token, restored.profile, offer(), expected_revision=0)
        assert not s.confirmed and s.confirmed_at is None
        with pytest.raises(ValueError):
            other.evaluate(1, 1, new.token, s.revision)
    finally:
        other.close()


def test_two_carriers_cannot_use_each_others_tokens_or_profiles(setup):
    store, path, _, _ = setup
    a, b = consent(store), consent(store, user=2)
    saved_a, saved_b = save(store, a), save(store, b, user=2)
    assert saved_a.version != saved_b.version
    with pytest.raises(PermissionError):
        store.load_profile(2, 2, a.token)
    with pytest.raises(PermissionError):
        store.put(2, 2, a.token, profile(), offer(), expected_revision=1)
    store.forget(1, 1)
    assert len(rows(path)) == 1
    assert store.load_profile(2, 2, b.token) == saved_b
    assert store.evaluate(2, 2, b.token, 1)['gap'] == '60.00'


@pytest.mark.parametrize('ids', [(1, 2), (3, 3), (True, True), (1.0, 1.0), (1, -1)])
def test_unauthorized_operations_rejected_before_database_access(setup, ids):
    store, _, _, _ = setup
    # Database closed: permission must be checked before even touching storage.
    store._db.close()
    for call in [lambda: store.disclosure(*ids), lambda: store.consent(*ids, 'x', 'session_only'),
                 lambda: store.load_profile(*ids, 'x'), lambda: store.forget(*ids),
                 lambda: store.save_profile(*ids, 'x', 1, expected_version=None)]:
        with pytest.raises(PermissionError):
            call()


def test_stale_expired_and_replayed_disclosure_tokens(setup):
    store, _, clock, _ = setup
    old = store.disclosure(1, 1)
    current = store.disclosure(1, 1)
    with pytest.raises(PermissionError):
        store.consent(1, 1, old.token, 'remember_profile')
    access = store.consent(1, 1, current.token, 'remember_profile')
    with pytest.raises(PermissionError):
        store.consent(1, 1, current.token, 'remember_profile')
    notice = store.disclosure(1, 1)
    clock.advance(300)
    with pytest.raises(PermissionError):
        store.consent(1, 1, notice.token, 'remember_profile')
    with pytest.raises(PermissionError):
        store.load_profile(1, 1, access.token)


def test_expiry_boundary_clears_active_session_but_preserves_unexpired_profile(setup):
    store, path, clock, _ = setup
    access = consent(store)
    saved = save(store, access)
    clock.advance(60)
    with pytest.raises(PermissionError):
        store.evaluate(1, 1, access.token, 1)
    assert len(rows(path)) == 1
    renewed = consent(store)
    assert store.load_profile(1, 1, renewed.token) == saved
    with pytest.raises(KeyError):
        store.get(1, 1, renewed.token)
    with pytest.raises(PermissionError):
        store.get(1, 1, access.token)


def test_profile_expiry_and_scheduled_cleanup(setup):
    store, path, clock, _ = setup
    save(store, consent(store))
    clock.advance(120)
    new = consent(store)
    assert store.load_profile(1, 1, new.token) is None
    assert rows(path) == []
    save(store, new)
    clock.advance(120)
    store.purge_expired()
    assert rows(path) == []
    with pytest.raises(PermissionError):
        store.get(1, 1, new.token)


def test_downgrade_deletes_saved_profile_and_invalidates_old_callbacks(setup):
    store, path, _, _ = setup
    old = consent(store)
    save(store, old)
    new = consent(store, choice='session_only')
    assert rows(path) == []
    with pytest.raises(PermissionError):
        store.evaluate(1, 1, old.token, 1)
    confirmed(store, new)
    assert store.evaluate(1, 1, new.token, 1)['revision'] == 1
    with pytest.raises(PermissionError):
        store.confirm(1, 1, old.token, 1)  # reused integer revision, different consent generation


def test_forget_works_without_live_consent_and_withdraws_all_state(setup):
    store, path, clock, _ = setup
    access = consent(store)
    save(store, access)
    clock.advance(60)
    store.forget(1, 1)
    assert rows(path) == []
    with pytest.raises(PermissionError):
        store.load_profile(1, 1, access.token)
    new = consent(store)
    assert store.load_profile(1, 1, new.token) is None


def test_saved_version_and_revision_checks_prevent_stale_replacement(setup):
    store, _, _, _ = setup
    access = consent(store)
    saved = save(store, access)
    store.put(1, 1, access.token, profile(target_all_mile_rpm='3'), offer(), expected_revision=1)
    with pytest.raises(ValueError):
        store.save_profile(1, 1, access.token, 1, expected_version=saved.version)
    with pytest.raises(ValueError):
        store.save_profile(1, 1, access.token, 2, expected_version=saved.version)
    store.confirm(1, 1, access.token, 2)
    with pytest.raises(ValueError):
        store.save_profile(1, 1, access.token, 2, expected_version=None)
    assert store.load_profile(1, 1, access.token) == saved
    updated = store.save_profile(1, 1, access.token, 2, expected_version=saved.version)
    assert updated.version != saved.version
    assert store.load_profile(1, 1, access.token).profile.target_all_mile_rpm == 3


def test_failed_deletion_still_withdraws_active_processing(setup):
    store, _, _, _ = setup
    access = consent(store)
    confirmed(store, access)
    store._db.close()  # represent unavailable storage, never report successful deletion
    with pytest.raises(sqlite3.ProgrammingError):
        store.forget(1, 1)
    with pytest.raises(PermissionError):
        store.evaluate(1, 1, access.token, 1)


def test_corrupt_profile_error_does_not_include_private_content(setup):
    store, _, _, _ = setup
    access = consent(store)
    save(store, access)
    with store._db:
        store._db.execute('UPDATE pilot_profiles SET profile=?', ('{"private-marker":true}',))
    with pytest.raises(ValueError, match='^Saved profile cannot be loaded$'):
        store.load_profile(1, 1, access.token)


def test_reads_do_not_extend_profile_retention(setup):
    store, _, clock, _ = setup
    saved = save(store, consent(store))
    clock.advance(59)
    access = consent(store)
    assert store.load_profile(1, 1, access.token).expires_at == saved.expires_at
    clock.advance(59)
    access = consent(store)
    assert store.load_profile(1, 1, access.token).expires_at == saved.expires_at
    clock.advance(2)
    assert store.load_profile(1, 1, access.token) is None


def test_failed_write_rolls_back_saved_profile(setup):
    store, _, _, _ = setup
    access = consent(store)
    saved = save(store, access)
    with store._db:
        store._db.execute('''CREATE TRIGGER fail_save BEFORE INSERT ON pilot_profiles
                             BEGIN SELECT RAISE(ABORT, 'test failure'); END''')
    with pytest.raises(sqlite3.IntegrityError):
        store.save_profile(1, 1, access.token, 1, expected_version=saved.version)
    assert store.load_profile(1, 1, access.token) == saved


def test_disclosure_states_limits_and_requires_explicit_choice(setup):
    store, _, _, _ = setup
    notice = store.disclosure(1, 1)
    assert 'Synthetic offline tests only.' in notice.text
    assert 'provider histories' in notice.text
    assert '60 seconds' in notice.text and '120 seconds' in notice.text
    with pytest.raises(ValueError):
        store.consent(1, 1, notice.token, 'unknown')
