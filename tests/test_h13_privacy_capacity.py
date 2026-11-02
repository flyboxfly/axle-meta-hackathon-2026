import pytest
from axle_hackathon.pilot_inbox import PilotInbox
from test_h13_inbox import inbox
from test_h13_memory import consent, save


def fill(s):
    with s._db:
        s._db.executemany('INSERT INTO pilot_updates VALUES (?, ?, ?, NULL, NULL, ?, NULL)',
                         [(i,'a','flow','completed') for i in range(10000)])


def test_full_inbox_accepts_bounded_privacy_and_withdraws_immediately(inbox):
    s,_,_=inbox;a=consent(s);save(s,a);fill(s)
    assert s.submit(1,1,10001,'forget',command_id=50)
    with pytest.raises(PermissionError):s.get(1,1,a.token)
    assert s._db.execute('SELECT count(*) FROM pilot_updates').fetchone()[0]==10000
    assert s._db.execute('SELECT count(*) FROM pilot_privacy').fetchone()[0]==1
    s.process_forget(1,1,10001)
    assert s._db.execute('SELECT count(*) FROM pilot_profiles').fetchone()[0]==0


def test_restart_duplicate_and_newer_privacy_coalesce_without_deleting_new_profile(inbox):
    s,path,policy=inbox;a=consent(s);save(s,a);fill(s)
    s.submit(1,1,10001,'forget',command_id=50);s.close()
    n=PilotInbox(path,{(1,1):'a'},policy)
    try:
        fresh=consent(n);saved=save(n,fresh)
        assert not n.submit(1,1,10001,'forget',command_id=50)
        assert not n.submit(1,1,10002,'forget',command_id=49)
        n.process_forget(1,1,10001)
        assert n.load_profile(1,1,fresh.token)==saved
        # A lower update ID after a transport sequence reset is independent of message order.
        assert n.submit(1,1,10000,'forget',command_id=51)
        for i in range(52,62):n.submit(1,1,20000+i,'forget',command_id=i)
        assert n._db.execute('SELECT count(*) FROM pilot_privacy').fetchone()[0]==1
    finally:n.close()


def test_privacy_update_cannot_be_reused_by_another_binding(inbox):
    s,_,_=inbox
    s.submit(1,1,10001,'forget',command_id=1)
    with pytest.raises(PermissionError):s.submit(2,2,10001,'forget',command_id=1)


def test_storage_failure_stops_active_processing_but_is_not_acknowledged(inbox):
    s,_,_=inbox;a=consent(s);save(s,a)
    s._db.execute('PRAGMA query_only=ON')
    with pytest.raises(Exception):s.submit(1,1,10001,'forget',command_id=1)
    with pytest.raises(PermissionError):s.get(1,1,a.token)
    s._db.execute('PRAGMA query_only=OFF')
