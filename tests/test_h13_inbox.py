import sqlite3
import pytest
from axle_hackathon.pilot_inbox import PilotInbox
from test_h13_memory import Clock, consent, save
from axle_hackathon.pilot_memory import MemoryPolicy


@pytest.fixture
def inbox(tmp_path):
    path = tmp_path / 'inbox.sqlite3'
    policy = MemoryPolicy(version='test', processing_notice='Invented offline records only')
    store = PilotInbox(path, {(1,1):'a',(2,2):'b'}, policy, clock=Clock())
    yield store, path, policy
    store.close()


def test_duplicate_and_single_claim(inbox):
    s, _, _ = inbox
    a = consent(s)
    save(s,a)
    assert s.submit(1,1,10,'evaluate',token=a.token,revision=1)
    assert not s.submit(1,1,10,'evaluate',token=a.token,revision=1)
    claim, revision = s.claim_evaluation(1,1,10,a.token)
    assert revision == 1
    with pytest.raises(ValueError): s.claim_evaluation(1,1,10,a.token)
    with pytest.raises(PermissionError): s.submit(2,2,10,'evaluate')
    with pytest.raises(ValueError): s.finish(2,2,10,claim,success=True)
    s.finish(1,1,10,claim,success=True)
    with pytest.raises(ValueError): s.finish(1,1,10,claim,success=True)


@pytest.mark.parametrize('sending', [False, True])
def test_restart_marks_inflight_uncertain_and_does_not_replay(inbox, sending):
    s, path, policy = inbox
    a=consent(s); save(s,a)
    s.submit(1,1,10,'evaluate',token=a.token,revision=1)
    claim,_=s.claim_evaluation(1,1,10,a.token)
    if sending:
        s.start_delivery(1,1,10,claim)
    s.close()
    new=PilotInbox(path,{(1,1):'a'},policy)
    try:
        assert not new.submit(1,1,10,'evaluate')
        assert new._db.execute('SELECT status FROM pilot_updates').fetchone()[0]=='uncertain'
        fresh=consent(new)
        with pytest.raises((KeyError,ValueError)): new.claim_evaluation(1,1,10,fresh.token)
    finally: new.close()


def test_deletion_failure_survives_restart(inbox):
    s,path,policy=inbox
    a=consent(s);save(s,a)
    with s._db:
        s._db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON pilot_profiles BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(sqlite3.IntegrityError): s.forget(1,1)
    s.close()
    new=PilotInbox(path,{(1,1):'a'},policy)
    try:
        with pytest.raises(sqlite3.IntegrityError): consent(new)
        with new._db: new._db.execute('DROP TRIGGER fail_delete')
        fresh=consent(new)
        assert new.load_profile(1,1,fresh.token) is None
    finally: new.close()


def test_forget_acceptance_is_durable_and_old_command_cannot_delete_new_profile(inbox):
    s,path,policy=inbox
    a=consent(s);save(s,a)
    assert s.submit(1,1,20,'forget')
    with pytest.raises(PermissionError): s.get(1,1,a.token)
    s.close()
    new=PilotInbox(path,{(1,1):'a'},policy)
    try:
        fresh=consent(new) # completes deletion before new consent
        saved=save(new,fresh)
        new.process_forget(1,1,20)
        assert new.load_profile(1,1,fresh.token)==saved
        assert not new.submit(1,1,20,'forget')
    finally:new.close()


def test_second_owner_rejected(inbox):
    _,path,policy=inbox
    with pytest.raises(RuntimeError,match='already has an owner'):
        PilotInbox(path,{(1,1):'a'},policy)


def test_changed_consent_cannot_claim_old_work(inbox):
    s,_,_=inbox
    a=consent(s);save(s,a)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    fresh=consent(s)
    from test_h13_memory import confirmed
    confirmed(s,fresh)
    with pytest.raises(ValueError):s.claim_evaluation(1,1,1,fresh.token)
