"""The rule forecast (plan 8.1): Decimal maths with ROUND_HALF_UP, eligible never below 0, P90 capped."""
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.rules.forecast import (MANUAL, RULE_V1, Forecast, Forecaster, ForecastInput, RuleBasedForecaster,
                                eligible_diners, manual_forecast, rule_p50_p90)

RATIO = Decimal("0.850")
BUFFER = Decimal("6.0")


def forecast(registered: int, opted_out: int, ratio=RATIO, buffer=BUFFER) -> Forecast:
    return RuleBasedForecaster().forecast(ForecastInput(registered=registered, opted_out=opted_out,
                                                        attendance_ratio=ratio, buffer_pct=buffer))


def test_plan_example_45_opted_out_gives_812_and_861():
    # 1000 - 45 = 955 -> P50 = round(811.75) = 812 -> P90 = ceil(860.72) = 861
    assert forecast(1000, 45) == Forecast(p50=812, p90=861, method=RULE_V1, model_version=None)


def test_demo_start_44_opted_out_gives_813_and_862():
    # demo script 0:00: 956 x 0.85 = 812.6 -> 813; 813 x 1.06 = 861.78 -> 862
    assert forecast(1000, 44) == Forecast(p50=813, p90=862, method=RULE_V1)


def test_rule_p50_p90_examples_from_the_plan():
    assert rule_p50_p90(956, RATIO, BUFFER) == (813, 862)
    assert rule_p50_p90(955, RATIO, BUFFER) == (812, 861)


@pytest.mark.parametrize("eligible, ratio, expected_p50", [
    (1625, Decimal("0.500"), 813),  # 812.5 exactly: half-up gives 813 (round() would give 812)
    (1623, Decimal("0.500"), 812),  # 811.5: half-up gives 812 (round() would also give 812)
    (5, Decimal("0.500"), 3),  # 2.5 -> 3 (banker's rounding would give 2)
    (1, Decimal("0.500"), 1),  # 0.5 -> 1
    (999, Decimal("0.001"), 1),  # 0.999 -> 1
    (499, Decimal("0.001"), 0),  # 0.499 -> 0
])
def test_p50_rounds_half_up_not_bankers(eligible, ratio, expected_p50):
    p50, _ = rule_p50_p90(eligible, ratio, Decimal("0.0"))
    assert p50 == expected_p50


def test_p90_is_the_ceiling_of_the_buffer():
    assert rule_p50_p90(100, Decimal("1.000"), Decimal("6.0")) == (100, 100)  # capped at eligible
    assert rule_p50_p90(200, Decimal("0.500"), Decimal("6.0")) == (100, 106)  # exactly 106.0 stays 106
    assert rule_p50_p90(200, Decimal("0.500"), Decimal("6.1")) == (100, 107)  # 106.1 -> 107


def test_p90_is_capped_at_the_eligible_count():
    # 100 eligible, everyone comes: P50 100, and the buffer can never add diners who don't exist
    assert forecast(100, 0, ratio=Decimal("1.000"), buffer=Decimal("20.0")) == Forecast(100, 100, RULE_V1)
    # 10 eligible x 0.95 = 9.5 -> 10; ceil(10 x 1.06) = 11 -> capped at 10
    assert forecast(10, 0, ratio=Decimal("0.950")) == Forecast(10, 10, RULE_V1)


def test_zero_buffer_gives_p90_equal_to_p50():
    assert forecast(1000, 45, buffer=Decimal("0.0")) == Forecast(812, 812, RULE_V1)


def test_eligible_is_never_below_zero():
    assert eligible_diners(100, 150) == 0
    assert eligible_diners(100, 100) == 0
    assert eligible_diners(100, 40) == 60
    assert forecast(100, 150) == Forecast(0, 0, RULE_V1)


def test_floats_are_refused():
    with pytest.raises(TypeError):
        rule_p50_p90(955, 0.85, BUFFER)
    with pytest.raises(TypeError):
        rule_p50_p90(955, RATIO, 6.0)


def test_rule_forecaster_fits_the_forecaster_port():
    forecaster: Forecaster = RuleBasedForecaster()  # the ML forecaster will implement the same method
    assert forecaster.forecast(ForecastInput(1000, 45, RATIO, BUFFER)).method == RULE_V1


def test_forecast_is_frozen():
    result = forecast(1000, 45)
    with pytest.raises(FrozenInstanceError):
        result.p50 = 1


def test_manual_forecast_keeps_the_managers_numbers():
    assert manual_forecast(900, 950) == Forecast(p50=900, p90=950, method=MANUAL)
    assert manual_forecast(0, 0) == Forecast(0, 0, MANUAL)
    # events may bring guests beyond the registered diners: no cap
    assert manual_forecast(1500, 1600).p90 == 1600


def test_manual_forecast_needs_p90_at_least_p50():
    with pytest.raises(ValueError):
        manual_forecast(900, 899)
    with pytest.raises(ValueError):
        manual_forecast(-1, 10)
