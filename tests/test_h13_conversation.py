import pytest
from fastapi.testclient import TestClient
from axle_hackathon.pilot_conversation import PilotConversation
from axle_hackathon.pilot_telegram import create_app
from test_h13_inbox import inbox
from test_h13_telegram import SECRET, update


def nonce(flow):
    return flow._flows['a']['nonce']


def reply(flow,answer):
    return flow.handle(1,1,f'/reply {nonce(flow)} {answer}')


def intake(flow, costs='1.25',target='2'):
    flow.handle(1,1,'/start')
    reply(flow,'session')
    reply(flow,'box_truck_26ft owned')
    reply(flow,'420 180 40')
    reply(flow,'20 6 feasible')
    reply(flow,target)
    return reply(flow,costs)


def test_full_synthetic_flow_and_correction(inbox):
    s,_,_=inbox;f=PilotConversation(s)
    review=intake(f)
    assert 'SYNTHETIC DRAFT' in review and 'payout: 420' in review
    token=f._flows['a']['token']
    with pytest.raises(ValueError):s.evaluate(1,1,token,1)
    old=nonce(f)
    f.handle(1,1,f'/confirm {old}')
    assert s.evaluate(1,1,token,1)['planning_cost_including_reserves']=='300.00'
    with pytest.raises(ValueError):f.handle(1,1,f'/confirm {old}')
    f.handle(1,1,f'/edit {nonce(f)} payout 600')
    with pytest.raises(ValueError):s.evaluate(1,1,token,2)
    f.handle(1,1,f'/confirm {nonce(f)}')
    assert s.evaluate(1,1,token,2)['decision']=='ACCEPT'


def test_unknown_costs_target_and_deadhead_remain_unknown(inbox):
    s,_,_=inbox;f=PilotConversation(s)
    intake(f,costs='skip',target='unknown')
    f.handle(1,1,f'/edit {nonce(f)} deadhead_miles unknown')
    f.handle(1,1,f'/confirm {nonce(f)}')
    result=s.evaluate(1,1,f._flows['a']['token'],2)
    assert result['decision']=='NEED_MORE_INFORMATION'
    assert result['planning_cost_including_reserves'] is None and result['total_miles'] is None


def test_invalid_answer_does_not_advance_or_change_snapshot(inbox):
    s,_,_=inbox;f=PilotConversation(s);intake(f)
    old=nonce(f)
    with pytest.raises(ValueError):f.handle(1,1,f'/edit {old} payout NaN')
    assert nonce(f)==old and s.get(1,1,f._flows['a']['token']).revision==1
    with pytest.raises(ValueError):f.handle(1,1,f'/edit {old} carrier b')


def test_equipment_unknown_does_not_invent_profile(inbox):
    s,_,_=inbox;f=PilotConversation(s);f.handle(1,1,'/start');reply(f,'session')
    answer=reply(f,'unknown')
    assert 'No costs or capabilities will be assumed' in answer
    with pytest.raises(KeyError):s.get(1,1,f._flows['a']['token'])


def test_rental_unknown_coverage_blocks_acceptance(inbox):
    s,_,_=inbox;f=PilotConversation(s);f.handle(1,1,'/start');reply(f,'session')
    reply(f,'box_truck_26ft rented');reply(f,'unknown')
    reply(f,'600 180 40');reply(f,'20 6 feasible');reply(f,'2');reply(f,'1.25')
    f.handle(1,1,f'/confirm {nonce(f)}')
    r=s.evaluate(1,1,f._flows['a']['token'],1)
    assert 'rental_maintenance_coverage' in r['missing']


def test_other_carrier_cannot_use_step_nonce(inbox):
    s,_,_=inbox;f=PilotConversation(s);f.handle(1,1,'/start')
    with pytest.raises(ValueError):f.handle(2,2,f'/reply {nonce(f)} session')
    with pytest.raises(PermissionError):f.handle(3,3,'/start')


def test_conversation_webhook_duplicate_has_no_second_effect(inbox):
    s,_,_=inbox;f=PilotConversation(s);sent=[]
    def send(chat,text):sent.append((chat,text));return True
    c=TestClient(create_app(s,webhook_secret=SECRET,allowed_host='testserver',conversation=f,send=send))
    headers={'X-Telegram-Bot-Api-Secret-Token':SECRET}
    def post(text,id):return c.post('/telegram/webhook',json=update(text,id=id),headers=headers)
    assert post('/start',1).status_code==200
    old=nonce(f)
    assert post('/start',1).json()['status']=='duplicate'
    assert nonce(f)==old and len(sent)==1
    assert post(f'/reply {old} session',2).status_code==200
    assert post('/forget',3).status_code==200
    assert 'a' not in f._flows


def test_expiry_purges_conversation_values(inbox):
    s,_,_=inbox;f=PilotConversation(s);intake(f)
    s._clock.advance(3600)
    f.purge_expired()
    assert f._flows=={}


def test_failed_send_not_replayed(inbox):
    s,_,_=inbox;f=PilotConversation(s);attempts=[]
    def send(chat,text):attempts.append(text);raise RuntimeError('private SDK body')
    c=TestClient(create_app(s,webhook_secret=SECRET,allowed_host='testserver',conversation=f,send=send))
    kwargs=dict(json=update('/start'),headers={'X-Telegram-Bot-Api-Secret-Token':SECRET})
    assert c.post('/telegram/webhook',**kwargs).status_code==503
    assert c.post('/telegram/webhook',**kwargs).json()['status']=='duplicate'
    assert len(attempts)==1


def test_remember_requires_explicit_save_after_confirmation(inbox):
    s,_,_=inbox;f=PilotConversation(s)
    f.handle(1,1,'/start');reply(f,'remember');reply(f,'box_truck_26ft owned')
    reply(f,'420 180 40');reply(f,'20 6 feasible');reply(f,'2');reply(f,'1.25')
    token=f._flows['a']['token']
    assert s.load_profile(1,1,token) is None
    with pytest.raises(ValueError):f.handle(1,1,f'/save {nonce(f)}')
    f.handle(1,1,f'/confirm {nonce(f)}')
    assert s.load_profile(1,1,token) is None
    f.handle(1,1,f'/save {nonce(f)}')
    assert s.load_profile(1,1,token).profile.equipment=='box_truck_26ft'


def test_complete_webhook_intake_to_mocked_model_delivery(inbox):
    from types import SimpleNamespace as NS
    from axle_hackathon.pilot_meta import PilotDelegator
    from axle_hackathon.pilot_telegram import run_evaluation
    from test_h13_meta import response
    s,_,_=inbox;f=PilotConversation(s);sent=[]
    def send(chat,text):sent.append(text);return True
    c=TestClient(create_app(s,webhook_secret=SECRET,allowed_host='testserver',conversation=f,send=send))
    headers={'X-Telegram-Bot-Api-Secret-Token':SECRET}
    def post(text,id):
        assert c.post('/telegram/webhook',json=update(text,id=id),headers=headers).status_code==200
    post('/start',1)
    for id,answer in enumerate(['session','box_truck_26ft owned','420 180 40','20 6 feasible','2','1.25'],2):
        step=sent[-1].split('\nStep: ')[1].split('\n')[0]
        post(f'/reply {step} {answer}',id)
    step=sent[-1].split('\nStep: ')[1].split('\n')[0]
    post(f'/confirm {step}',8);post('/evaluate',9)
    d=PilotDelegator(s,NS(responses=NS(create=lambda **kw:response())))
    run_evaluation(s,d,send,user=1,chat=1,update_id=9)
    assert 'NEGOTIATE' in sent[-1] and '$300.00' in sent[-1]


@pytest.mark.parametrize('action',['forget','expire','close'])
def test_memory_lifecycle_clears_conversation_without_transport_cleanup(inbox,action):
    s,_,_=inbox;f=PilotConversation(s);intake(f)
    if action=='forget':s.forget(1,1)
    elif action=='close':s.close()
    else:
        s._clock.advance(3600)
        s.purge_expired()
    assert f._flows=={}
