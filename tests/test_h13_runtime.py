from threading import Event
from concurrent.futures import ThreadPoolExecutor
from axle_hackathon.pilot_runtime import PilotWorker
from axle_hackathon.pilot_inbox import PilotInbox
from test_h13_inbox import inbox
from test_h13_telegram import ready


def worker(s, calls, **limits):
    class D:
        def evaluate(self,*args):
            calls.append(args[0])
            return {'evaluation':s.evaluate(*args)}
    return PilotWorker(s,D(),lambda *_:True,global_limit=limits.get('global_limit',2),
                       carrier_limit=limits.get('carrier_limit',1))


def test_caps_persist_across_worker_and_inbox_restart(inbox):
    s,path,policy=inbox;a=ready(s);calls=[]
    w=worker(s,calls)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    assert w.tick()=='completed'
    s.submit(1,1,2,'evaluate',token=a.token,revision=1)
    assert w.tick()=='uncertain' and calls==[1]
    s.close()
    new=PilotInbox(path,{(1,1):'a'},policy)
    try:
        a=ready(new);w=worker(new,calls)
        new.submit(1,1,3,'evaluate',token=a.token,revision=1)
        assert w.tick()=='uncertain' and calls==[1]
    finally:new.close()


def test_global_cap_is_shared_across_carriers(inbox):
    s,_,_=inbox;calls=[];w=worker(s,calls,global_limit=1)
    from test_h13_memory import consent, confirmed
    for user in (1,2):
        a=consent(s,user);confirmed(s,a,user)
        s.submit(user,user,user,'evaluate',token=a.token,revision=1)
    assert w.tick()=='completed'
    assert w.tick()=='uncertain' and len(calls)==1


def test_failure_consumes_reservation_and_is_not_retried(inbox):
    s,_,_=inbox;a=ready(s);calls=[]
    class D:
        def evaluate(self,*args):calls.append(1);raise RuntimeError('invented failure')
    w=PilotWorker(s,D(),lambda *_:True,global_limit=1,carrier_limit=1)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    assert w.tick()=='uncertain'
    assert w.tick()=='idle' and calls==[1]
    assert s._db.execute('SELECT attempts FROM pilot_budget').fetchone()==(1,)


def test_busy_worker_and_close_do_not_start_more_work(inbox):
    s,_,_=inbox;a=ready(s);started,release=Event(),Event()
    class D:
        def evaluate(self,*args):
            started.set();assert release.wait(2)
            return {'evaluation':s.evaluate(*args)}
    w=PilotWorker(s,D(),lambda *_:True,global_limit=1,carrier_limit=1)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task=pool.submit(w.tick)
        try:
            assert started.wait(1)
            assert w.tick()=='busy'
            assert worker(s,[]).tick()=='busy'
            w.close()
        finally:release.set()
        assert task.result(timeout=1)=='completed'
    assert w.tick()=='closed'


def test_privacy_precedes_evaluation_even_with_spent_budget(inbox):
    s,_,_=inbox;a=ready(s);calls=[];w=worker(s,calls)
    s.submit(1,1,1,'evaluate',token=a.token,revision=1)
    assert w.tick()=='completed'
    s.submit(1,1,2,'forget')
    assert w.tick()=='idle'
    assert s._db.execute('SELECT status FROM pilot_privacy').fetchone()==('completed',)
    assert calls==[1]
