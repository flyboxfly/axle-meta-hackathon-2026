"""Invented planning inputs only; no provider or carrier records."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from axle_hackathon.pilot import (
    CostItem, FuelEstimate, PeriodAllocation, PilotSessions, ProfileMetadata, SoftwareRecord,
)
from test_h13_pilot import profile, offer, result


def replace_costs(*replacements):
    by_name = {i.name: i for i in profile().items}
    by_name.update({i.name: i for i in replacements})
    return profile(items=tuple(by_name.values()))


def fuel(**changes):
    values = dict(price_per_us_gallon='4', miles_per_us_gallon='10')
    values.update(changes)
    return CostItem(name='fuel', basis='fuel_mpg', fuel=FuelEstimate(**values), source='fixture')


def periodic(name='insurance', **changes):
    values = dict(cost_period='month', utilization_period='month', operating_miles='6000')
    values.update(changes)
    return CostItem(name=name, amount='1500', basis='per_period',
                    allocation=PeriodAllocation(**values, source='carrier supplied forecast'),
                    source='fixture monthly planning amount')


def test_normalized_costs_use_whole_trip_and_preserve_assumptions():
    # 240 miles: fuel 96; labor 150; insurance 60; other costs/reserve 116.
    p = replace_costs(fuel(), periodic(), CostItem(name='driver', amount='25',
                      basis='per_hour', source='fixture including dwell'))
    r = result(p, offer(trip_hours='6', payout='600'))
    assert r['planning_cost_including_reserves'] == '422.00'
    assert r['planning_surplus'] == '178.00'
    assert r['contingency'] == '10.00'
    assert r['decision'] == 'ACCEPT'
    lines = {i['name']: i for i in r['cost_breakdown']}
    assert lines['fuel']['amount'] == '96.00'
    assert lines['driver']['amount'] == '150.00'
    assert lines['insurance']['amount'] == '60.00'
    assert p.items[2].allocation.operating_miles == Decimal('6000')


@pytest.mark.parametrize('field', ['price_per_us_gallon', 'miles_per_us_gallon'])
def test_missing_fuel_component_is_not_zero(field):
    r = result(replace_costs(fuel(**{field: None})), offer(payout='600'))
    assert 'fuel:' + field in r['missing']
    assert r['planning_cost_including_reserves'] is None
    assert r['planning_surplus'] is None
    assert r['decision'] == 'NEED_MORE_INFORMATION'


def test_hourly_time_unknown_and_explicit_zero_are_distinct():
    p = replace_costs(CostItem(name='driver', amount='25', basis='per_hour', source='fixture'))
    r = result(p, offer(payout='600'))
    assert 'trip_hours' in r['missing']
    assert r['planning_cost_including_reserves'] is None
    assert result(p, offer(trip_hours='0'))['planning_cost_including_reserves'] == '232.00'
    assert result(p, offer(trip_hours='8'))['planning_cost_including_reserves'] == '432.00'


def test_period_utilization_unknown_blocks_total():
    r = result(replace_costs(periodic(operating_miles=None)))
    assert 'utilization:insurance' in r['missing']
    assert r['planning_cost_including_reserves'] is None


def test_weekly_rental_base_and_mileage_are_separate():
    base = CostItem(name='truck_base', amount='490', basis='per_period',
        allocation=PeriodAllocation(cost_period='week', utilization_period='week',
                                    operating_miles='1500', source='fixture forecast'),
        source='fixture weekly rental')
    r = result(replace_costs(base))
    lines = {i['name']: i['amount'] for i in r['cost_breakdown']}
    assert lines['truck_base'] == '78.40'
    assert lines['rental_mileage'] == '36.00'
    assert lines['maintenance'] == '0.00'
    assert r['planning_cost_including_reserves'] == '340.40'


@pytest.mark.parametrize('period,miles,expected', [
    ('week', '1500', '532.00'), ('month', '6000', '352.00'), ('year', '72000', '297.00'),
])
def test_period_allocation_respects_declared_utilization(period, miles, expected):
    p = replace_costs(periodic(cost_period=period, utilization_period=period, operating_miles=miles))
    assert result(p)['planning_cost_including_reserves'] == expected


def test_incompatible_periods_and_ambiguous_methods_rejected():
    with pytest.raises(ValidationError):
        periodic(utilization_period='week')
    with pytest.raises(ValidationError):
        CostItem(name='insurance', amount='1500', basis='per_period', source='fixture')
    with pytest.raises(ValidationError):
        CostItem(name='fuel', amount='.4', basis='fuel_mpg', fuel=fuel().fuel, source='fixture')
    with pytest.raises(ValidationError):
        CostItem(name='driver', basis='fuel_mpg', fuel=fuel().fuel, source='fixture')
    with pytest.raises(ValidationError):
        CostItem(name='fuel', amount='.4', basis='per_mile', fuel=fuel().fuel, source='fixture')
    with pytest.raises(ValidationError):
        CostItem(name='insurance', amount='20', basis='per_trip',
                 allocation=periodic().allocation, source='fixture')


@pytest.mark.parametrize('value', ['0', '-1', 'NaN', 'Infinity'])
def test_invalid_mpg_and_utilization(value):
    with pytest.raises(ValidationError):
        fuel(miles_per_us_gallon=value)
    with pytest.raises(ValidationError):
        periodic(operating_miles=value)


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity'])
def test_invalid_fuel_price_or_hours(value):
    with pytest.raises(ValidationError):
        fuel(price_per_us_gallon=value)
    with pytest.raises(ValidationError):
        offer(trip_hours=value)


def test_explicit_zero_fuel_price_and_unrounded_intermediates():
    assert result(replace_costs(fuel(price_per_us_gallon='0')))['planning_cost_including_reserves'] == '216.00'
    # 240 / 7 * 4.10, rounded only for presentation, not first to a CPM.
    r = result(replace_costs(fuel(price_per_us_gallon='4.10', miles_per_us_gallon='7')))
    assert r['planning_cost_including_reserves'] == '356.57'


def test_cpm_excluded_period_cost_added_once_and_overlap_still_rejected():
    included = tuple(i.name for i in profile().items if i.name != 'insurance')
    p = profile(mode='all_in_cpm', cpm='1', cpm_includes=included, items=(periodic(),))
    r = result(p)
    assert r['declared_cpm_cost'] == '240.00'
    assert r['planning_cost_including_reserves'] == '300.00'
    with pytest.raises(ValidationError):
        profile(mode='all_in_cpm', cpm='1', cpm_includes=included, items=(fuel(), periodic()))


def test_metadata_software_and_revised_assumptions_require_fresh_confirmation():
    metadata = ProfileMetadata(unit_id='test-unit', carrier_role='owner_operator',
        effective_at='2026-10-31T08:00:00-04:00', recorded_at='2026-10-31T13:00:00-04:00')
    software = tuple(SoftwareRecord(name=n, status=s, source='fixture') for n, s in
                     [('MileIQ', 'subscribed'), ('DAT', 'planned'), ('Axle', 'interested')])
    p = profile(metadata=metadata, software=software)
    s = PilotSessions({(1, 1): 'a'})
    s.put(1, 1, p, offer(), expected_revision=0)
    confirmed = s.confirm(1, 1, 1)
    assert confirmed.confirmed_at.utcoffset().total_seconds() == 0
    assert s.evaluate(1, 1, 1)['confirmed_at'] == confirmed.confirmed_at.isoformat()
    p2 = replace_costs(periodic())
    updated = s.put(1, 1, p2, offer(), expected_revision=1)
    assert updated.confirmed_at is None and not updated.confirmed
    with pytest.raises(ValueError):
        s.evaluate(1, 1, 2)
    with pytest.raises(ValueError):
        s.evaluate(1, 1, 1)
    s.confirm(1, 1, 2)
    assert s.evaluate(1, 1, 2)['planning_cost_including_reserves'] == '352.00'
    with pytest.raises(ValidationError):
        metadata.unit_id = 'other'
    with pytest.raises(ValidationError):
        ProfileMetadata(effective_at='2026-10-31T08:00:00', recorded_at=metadata.recorded_at)
    with pytest.raises(ValidationError):
        SoftwareRecord(name='DAT', status='authorized', source='fixture')
