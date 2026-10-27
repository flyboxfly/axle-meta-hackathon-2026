"""Fake model transport plus actual FastAPI handlers; no paid inference."""
import json
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from axle_hackathon.app import app
from axle_hackathon.external_agent import delegate_external, synthetic_request, DelegationFailure


def selection(**updates):
    call = NS(type='function_call',status='completed',name='evaluate_freight_opportunity',
              arguments=synthetic_request().opportunity.model_dump_json(),call_id='fake-call')
    return NS(id='fake-first',status='completed',output=[call],**updates)


def final():
    return NS(id='fake-final',status='completed',output=[],output_text='Synthetic result received.')


class Model:
    def __init__(self, first=None, last=None):
        self.responses=self; self.calls=[]; self.first=first or selection(); self.last=last or final()
    def create(self, **kwargs):
        self.calls.append(kwargs)
        value=self.first if len(self.calls)==1 else self.last
        if isinstance(value,Exception): raise value
        return value


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setenv('AXLE_DEMO_TOKEN','offline')
    return TestClient(app,headers={'Authorization':'Bearer offline'})


def test_round_trip_returns_full_canonical_envelope(http):
    model=Model(); result=delegate_external(model,http,synthetic_request())
    assert len(model.calls)==2
    assert 'tool_choice' not in model.calls[0]
    assert model.calls[1]['previous_response_id']=='fake-first'
    item=model.calls[1]['input'][0]
    assert item['call_id']=='fake-call' and item['type']=='function_call_output'
    envelope=json.loads(item['output'])
    assert envelope['evaluation']['revenue_gap_to_target']=='60.00'
    assert envelope['evaluation']['estimated_operating_cost']=='290.00'
    assert result['status']=='round_trip_completed'
    assert result['model_prose_validated'] is False
    assert 'answer' not in result
    assert 'benchmark' not in model.calls[0]['tools'][0]['parameters']['properties']


@pytest.mark.parametrize('kind',['incomplete','none','multiple','unknown','call_incomplete','changed','injection'])
def test_bad_selection_never_reaches_http(kind):
    first=selection()
    if kind=='incomplete': first.status='incomplete'
    elif kind=='none': first.output=[]
    elif kind=='multiple': first.output*=2
    elif kind=='unknown': first.output[0].name='other'
    elif kind=='call_incomplete': first.output[0].status='in_progress'
    else:
        data=json.loads(first.output[0].arguments)
        data['payout' if kind=='changed' else 'benchmark']='1'
        first.output[0].arguments=json.dumps(data)
    http=NS(post=lambda *a,**k:pytest.fail('HTTP reached'))
    model=Model(first=first)
    with pytest.raises(DelegationFailure,match='tool_selection'):
        delegate_external(model,http,synthetic_request())
    assert len(model.calls)==1


@pytest.mark.parametrize('kind',['timeout','incomplete','extra_call','empty'])
def test_followup_failure_returns_no_partial_success(http,kind):
    last=final()
    if kind=='timeout': last=TimeoutError('private provider text')
    elif kind=='incomplete': last.status='incomplete'
    elif kind=='extra_call': last.output=selection().output
    else: last.output_text=' '
    model=Model(last=last)
    with pytest.raises(DelegationFailure,match='after_tool') as error:
        delegate_external(model,http,synthetic_request())
    assert 'private' not in str(error.value) and len(model.calls)==2


def test_http_failure_prevents_followup(http):
    http.headers['Authorization']='Bearer wrong'
    model=Model()
    with pytest.raises(DelegationFailure,match='axle_http'):
        delegate_external(model,http,synthetic_request())
    assert len(model.calls)==1


def test_logs_redacted(caplog):
    model=Model(first=TimeoutError('secret credential and submitted facts'))
    with pytest.raises(DelegationFailure):
        delegate_external(model,None,synthetic_request())
    assert 'stage=tool_selection' in caplog.text
    assert 'secret credential' not in caplog.text
