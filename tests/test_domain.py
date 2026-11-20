from decimal import Decimal
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate


def test_interpolated(cases):
    actual, proof = evaluate(cases['interpolated'])
    assert actual == Decimal('15.000')
    assert str(dict((label, value) for label, value, _ in proof)['判批']) == '达标'


def test_gap(cases):
    # TRAP-101
    actual, proof = evaluate(cases['gap'])
    assert actual == Decimal('10.000')
    assert str(dict((label, value) for label, value, _ in proof)['判批']) == '保温不足'


def test_fahrenheit(cases):
    # TRAP-15
    actual, proof = evaluate(cases['fahrenheit'])
    assert actual == Decimal('5.040')
    assert str(dict((label, value) for label, value, _ in proof)['判批']) == '达标'


def test_dip_breaks(cases):
    actual, proof = evaluate(cases['dip_breaks'])
    assert actual == Decimal('10.000')
    assert str(dict((label, value) for label, value, _ in proof)['判批']) == '保温不足'


def test_exact(cases):
    actual, proof = evaluate(cases['exact'])
    assert actual == Decimal('4.000')
    assert str(dict((label, value) for label, value, _ in proof)['判批']) == '达标'


def test_point_only(cases):
    actual, proof = evaluate(cases['point_only'])
    assert actual == Decimal('0.000')
    assert str(dict((label, value) for label, value, _ in proof)['判批']) == '保温不足'


def test_conflicting_tick(cases):
    # TRAP-14
    with pytest.raises(DataError) as error:
        evaluate(cases['conflicting_tick'])
    assert error.value.code == 'TEMP_CONFLICT'


def test_single_point(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['single_point'])
    assert error.value.code == 'TEMP_COVERAGE'


def test_bad_scale(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['bad_scale'])
    assert error.value.code == 'TEMP_SCALE'
