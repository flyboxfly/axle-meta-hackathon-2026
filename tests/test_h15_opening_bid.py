"""Offline synthetic arithmetic cases, not owner pricing or model evidence."""
from decimal import Decimal
import pytest
from pydantic import ValidationError
from axle_hackathon.opening_bid import OpeningBidInputs, calculate_opening_bid


def inputs(**changes):
    values = dict(revision=1, loaded_miles='12.86', deadhead_miles='3.5',
        reposition_miles='0', operating_cpm='1.25',
        expense_basis='all_operating_expenses', target_all_mile_rpm='2.50',
        minimum_job_charge='100', pricing_source='synthetic unit test')
    return OpeningBidInputs(**(values | changes))


def test_short_trip_uses_minimum_without_inventing_payout():
    result = calculate_opening_bid(inputs())
    assert result['total_miles'] == '16.36'
    assert result['estimated_operating_cost'] == '20.45'
    assert result['target_revenue'] == '40.90'
    assert result['opening_bid'] == '100.00'
    assert result['estimated_operating_surplus'] == '79.55'
    assert result['status'] == 'PRELIMINARY_DRAFT'
    assert 'payout' not in result


def test_target_revenue_can_exceed_minimum():
    result = calculate_opening_bid(inputs(loaded_miles='100'))
    assert result['opening_bid'] == '258.75'


@pytest.mark.parametrize('field', ['deadhead_miles', 'reposition_miles',
    'operating_cpm', 'target_all_mile_rpm', 'minimum_job_charge'])
def test_unknown_is_never_zero(field):
    result = calculate_opening_bid(inputs(**{field: None}))
    assert field in result['missing']
    assert result['opening_bid'] is None


@pytest.mark.parametrize('cost', ['2.50', '3.00'])
def test_nonpositive_surplus_requires_review(cost):
    result = calculate_opening_bid(inputs(operating_cpm=cost, minimum_job_charge='0'))
    assert result['opening_bid'] is None
    assert result['pricing_issue']


def test_rounding_does_not_create_apparent_positive_surplus():
    result = calculate_opening_bid(inputs(loaded_miles='1', deadhead_miles='0',
        operating_cpm='1.001', target_all_mile_rpm='1.002', minimum_job_charge='0'))
    assert result['opening_bid'] is None


@pytest.mark.parametrize('changes', [dict(operating_cpm='NaN'),
    dict(deadhead_miles='-1'), dict(expense_basis='fuel_only'),
    dict(revision=True), dict(payout='0')])
def test_invalid_pricing_rejected(changes):
    with pytest.raises(ValidationError):
        inputs(**changes)


def test_revised_inputs_are_separate_immutable_calculations():
    original = inputs()
    revised = inputs(revision=2, minimum_job_charge='150')
    assert calculate_opening_bid(original)['opening_bid'] == '100.00'
    assert calculate_opening_bid(revised)['opening_bid'] == '150.00'
    assert original.minimum_job_charge == Decimal('100')
    with pytest.raises(ValidationError):
        original.minimum_job_charge = Decimal('150')
