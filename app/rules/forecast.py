"""Forecast rule (plan 8.1): the Forecaster port, the Forecast result and RuleBasedForecaster (RULE_V1).

Pure Python: no FastAPI, no database. Services load the numbers, call this, and save the result.

    optedOut = count(opt_out rows for kitchen, slot, date) + meal.extra_opt_outs
    eligible = max(0, registered - optedOut)
    P50      = round_half_up(eligible x attendance_ratio)
    P90      = min(eligible, ceil(P50 x (1 + buffer_pct / 100)))
    Example: 1000 - 45 = 955 -> P50 = round(811.75) = 812 -> P90 = ceil(860.72) = 861

All maths uses Decimal: Python's round() does banker's rounding (round(812.5) == 812) and floats drift.

The Forecaster protocol is the port the team's own ML model (trained on our mess data) will implement
later; the cook card, T-90 and SafeClock rules only ever see a Forecast.
"""
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

RULE_V1 = "RULE_V1"
MANUAL = "MANUAL"


@dataclass(frozen=True)
class ForecastInput:
    registered: int  # registered diners for this meal
    opted_out: int  # opt-out rows + the "opt-outs from another app" number
    attendance_ratio: Decimal  # share of eligible diners who usually come (R1 door tally), 0..1
    buffer_pct: Decimal  # extra % on top of P50 for the high forecast, e.g. Decimal("6.0")


@dataclass(frozen=True)
class Forecast:
    p50: int  # expected diners
    p90: int  # high forecast
    method: str  # RULE_V1 / MANUAL / ML_... (later)
    model_version: str | None = None


class Forecaster(Protocol):
    """RuleBasedForecaster now; the team's own ML forecaster implements the same method later."""

    def forecast(self, inp: ForecastInput) -> Forecast: ...


def eligible_diners(registered: int, opted_out: int) -> int:
    """Registered minus opted out, never below zero (more opt-outs than diners still means 0)."""
    return max(0, registered - opted_out)


def rule_p50_p90(eligible: int, ratio: Decimal, buffer_pct: Decimal) -> tuple[int, int]:
    """(956, 0.850, 6.0) -> (813, 862); (955, 0.850, 6.0) -> (812, 861)."""
    if not isinstance(ratio, Decimal) or not isinstance(buffer_pct, Decimal):
        raise TypeError("ratio and buffer_pct must be Decimal, never float")
    p50 = int((Decimal(eligible) * ratio).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    p90 = min(eligible, math.ceil(p50 * (1 + buffer_pct / 100)))
    return p50, p90


class RuleBasedForecaster:
    """The day-1 rule (method RULE_V1)."""

    def forecast(self, inp: ForecastInput) -> Forecast:
        eligible = eligible_diners(inp.registered, inp.opted_out)
        p50, p90 = rule_p50_p90(eligible, inp.attendance_ratio, inp.buffer_pct)
        return Forecast(p50=p50, p90=p90, method=RULE_V1)


def manual_forecast(p50: int, p90: int) -> Forecast:
    """The manager's own numbers (events, caterers, override): P50 = expected, P90 = high.

    Not capped at the eligible count: an event can bring guests who are not registered diners.
    The reason is checked and stored by the service (meal.override_reason)."""
    if p50 < 0:
        raise ValueError("P50 must not be negative")
    if p90 < p50:
        raise ValueError("P90 must not be below P50")
    return Forecast(p50=p50, p90=p90, method=MANUAL)
