from decimal import Decimal
import pytest
from pydantic import ValidationError
from axle_hackathon.pilot import Profile, CostItem, Opportunity, Snapshot, PilotSessions, calculate


def profile(**changes):
    values = dict(equipment='box_truck_26ft', arrangement='rented', mode='itemized',
        maintenance_covered_by_rental=True, target_all_mile_rpm='2', source='test confirmation',
        items=tuple(CostItem(name=n, amount=a, basis=b, source='test') for n,a,b in [
        ('fuel','0.4','per_mile'), ('driver','80','per_trip'), ('insurance','20','per_trip'),
        ('truck_base','50','per_trip'), ('rental_mileage','0.15','per_mile'),
        ('maintenance','0','per_mile'), ('tolls','20','per_trip'),
        ('miscellaneous','0','per_trip'), ('contingency','10','per_trip')]))
    values.update(changes)
    return Profile(**values)


def offer(**changes):
    values=dict(payout='420', loaded_miles='180', deadhead_miles='40', reposition_miles='20',
        schedule='feasible', scope='dock to dock', origin='real_offer',
        operation='hypothetical', source='test fixture, not real carrier data')
    values.update(changes)
    return Opportunity(**values)


def result(p=None, o=None):
    return calculate(Snapshot(1,p or profile(),o or offer(),True))


def test_rental_all_miles_and_reserve():
    r=result()
    assert r['total_miles']=='240'
    assert r['planning_cost_including_reserves']=='312.00'
    assert r['planning_surplus']=='108.00'
    assert r['contingency']=='10.00'
    assert r['gap']=='60.00'
    assert r['decision']=='NEGOTIATE'
    assert r['operating_scenario']=='hypothetical'


def test_included_cpm_and_excluded_toll():
    names=tuple(i.name for i in profile().items if i.name!='tolls')
    p=profile(mode='all_in_cpm',cpm='1',cpm_includes=names,
              items=(CostItem(name='tolls',amount='20',basis='per_trip',source='test'),))
    assert result(p)['planning_cost_including_reserves']=='260.00'
    assert result(p)['contingency'] is None


@pytest.mark.parametrize('field', ['deadhead_miles','reposition_miles'])
def test_unknown_miles(field):
    r=result(o=offer(**{field:None}))
    assert r['total_miles'] is None
    assert r['planning_surplus'] is None
    assert r['decision']=='NEED_MORE_INFORMATION'


def test_unknown_cost_and_target():
    p=profile(items=tuple(i for i in profile().items if i.name!='insurance'),target_all_mile_rpm=None)
    r=result(p)
    assert 'cost:insurance' in r['missing']
    assert r['gap'] is None and r['planning_cost_including_reserves'] is None


@pytest.mark.parametrize('schedule,decision',[('unknown','NEED_MORE_INFORMATION'),('conflict','DECLINE'),('feasible','ACCEPT')])
def test_schedule(schedule,decision):
    assert result(o=offer(payout='600',schedule=schedule))['decision']==decision


def test_duplicate_covered_maintenance_and_mixed_modes():
    with pytest.raises(ValidationError):
        profile(items=profile().items+(profile().items[0],))
    with pytest.raises(ValidationError):
        profile(items=tuple(i for i in profile().items if i.name!='maintenance')+
            (CostItem(name='maintenance',amount='.1',basis='per_mile',source='test'),))
    with pytest.raises(ValidationError):
        profile(cpm='1')
    with pytest.raises(ValidationError):
        profile(mode='all_in_cpm',cpm='1',cpm_includes=('fuel',))


@pytest.mark.parametrize('value',['NaN','Infinity','-1'])
def test_invalid_money(value):
    with pytest.raises(ValidationError):
        offer(payout=value)


def test_two_carriers_revisions_and_unauthorized_chat():
    sessions=PilotSessions({(1,1):'a',(2,2):'b'})
    a=sessions.put(1,1,profile(),offer(),expected_revision=0)
    sessions.put(2,2,profile(),offer(payout='800'),expected_revision=0)
    with pytest.raises(PermissionError): sessions.get(1,2)
    with pytest.raises(PermissionError): sessions.put(3,3,profile(),offer(),expected_revision=0)
    with pytest.raises(ValueError): sessions.evaluate(1,1,a.revision)
    sessions.confirm(1,1,1)
    assert sessions.evaluate(1,1,1)['gap']=='60.00'
    sessions.put(1,1,profile(),offer(scope='added stop',payout='500'),expected_revision=1)
    with pytest.raises(ValueError): sessions.confirm(1,1,1)
    with pytest.raises(ValueError): sessions.evaluate(1,1,1)
    with pytest.raises(ValueError): sessions.evaluate(1,1,2)
    assert sessions.get(2,2).opportunity.payout==Decimal('800')
    with pytest.raises(ValidationError): a.profile.target_all_mile_rpm=Decimal('1')
    with pytest.raises(ValueError): sessions.put(1,1,profile(),offer(),expected_revision=1)


def test_unknown_item_amount_and_coverage():
    items=tuple(CostItem(name=i.name, amount=None if i.name=='insurance' else i.amount,
                        basis=i.basis, source=i.source) for i in profile().items)
    assert result(profile(items=items))['planning_cost_including_reserves'] is None
    assert result(profile(maintenance_covered_by_rental=None))['decision']=='NEED_MORE_INFORMATION'


def test_cpm_overlap_and_invalid_numbers():
    with pytest.raises(ValidationError):
        profile(mode='all_in_cpm',cpm='1',cpm_includes=tuple(i.name for i in profile().items))
    with pytest.raises(ValidationError):
        profile(cpm='Infinity')
    with pytest.raises(ValidationError):
        offer(loaded_miles='0')


def test_cost_and_target_change_require_confirmation():
    s=PilotSessions({(1,1):'a'})
    s.put(1,1,profile(),offer(),expected_revision=0)
    s.confirm(1,1,1)
    s.put(1,1,profile(target_all_mile_rpm='3'),offer(),expected_revision=1)
    with pytest.raises(ValueError): s.evaluate(1,1,2)
    s.confirm(1,1,2)
    assert s.evaluate(1,1,2)['gap']=='300.00'
