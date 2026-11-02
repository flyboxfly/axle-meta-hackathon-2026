import pytest
from fastapi.testclient import TestClient
from axle_hackathon.pilot_conversation import PilotConversation
from axle_hackathon.pilot_inbox import PilotInbox
from axle_hackathon.pilot_telegram import create_app
from test_h13_inbox import inbox
from test_h13_telegram import update, SECRET


def app(s):
    flow=PilotConversation(s)
    return flow,TestClient(create_app(s,webhook_secret=SECRET,allowed_host='testserver',
                                     conversation=flow,send=lambda chat,text:True))


def post(c,text,update_id,message_id):
    payload=update(text,id=update_id);payload['message']['message_id']=message_id
    return c.post('/telegram/webhook',json=payload,headers={'X-Telegram-Bot-Api-Secret-Token':SECRET})


@pytest.mark.parametrize('old_command',['/start','/forget'])
def test_delayed_unseen_command_cannot_reset_newer_session(inbox,old_command):
    s,_,_=inbox;f,c=app(s)
    assert post(c,'/start',100,10).status_code==200
    nonce=f._flows['a']['nonce']
    assert post(c,old_command,101,9).json()['status']=='stale'
    assert f._flows['a']['nonce']==nonce
    assert s._db.execute('SELECT count(*) FROM pilot_deletions').fetchone()[0]==0


def test_ordering_survives_restart_and_does_not_depend_on_update_id(inbox):
    s,path,policy=inbox;f,c=app(s)
    post(c,'/start',1000,100);s.close()
    n=PilotInbox(path,{(1,1):'a'},policy)
    try:
        f,c=app(n)
        assert post(c,'/forget',1001,99).json()['status']=='stale'
        assert post(c,'/start',1,101).json()['status']=='processed'
    finally:n.close()


def test_failed_admission_does_not_advance_order(inbox):
    s,_,_=inbox;f,c=app(s)
    post(c,'/start',1,1)
    with s._db:
        s._db.executemany('INSERT INTO pilot_updates VALUES (?, ?, ?, NULL,NULL,?,NULL)',
                         [(i,'a','flow','completed') for i in range(2,10001)])
    assert post(c,'/start',20000,2).status_code==503
    assert not s.stale_message(1,1,2)
    assert post(c,'/forget',20001,3).status_code==200


def test_shared_carrier_bindings_cannot_bypass_order_via_other_chat(tmp_path):
    from axle_hackathon.pilot_memory import MemoryPolicy
    s=PilotInbox(tmp_path/'scope.sqlite3',{(1,1):'a',(2,2):'a'},
                 MemoryPolicy(version='test',processing_notice='Invented only'))
    try:
        with pytest.raises(ValueError,match='One approved'):
            create_app(s,webhook_secret=SECRET,allowed_host='testserver')
    finally:s.close()
