"""Opt-out checks with no database: the per-IP rate limiter and the hostel ID format."""
from datetime import datetime, timedelta

import pytest

from app.core.clock import IST
from app.core.errors import ApiError
from app.services.opt_outs import RateLimiter, clean_hostel_id

T0 = datetime(2026, 10, 30, 8, 30, tzinfo=IST)


def test_limit_per_key_within_the_window():
    limiter = RateLimiter()
    assert [limiter.hit("1.2.3.4", T0, limit=3, window_s=60) for _ in range(3)] == [None, None, None]
    assert limiter.hit("1.2.3.4", T0, limit=3, window_s=60) == 60  # wait a full minute
    assert limiter.hit("5.6.7.8", T0, limit=3, window_s=60) is None  # another phone is not affected
    assert limiter.hit("1.2.3.4", T0 + timedelta(seconds=45), limit=3, window_s=60) == 15
    assert limiter.hit("1.2.3.4", T0 + timedelta(seconds=60), limit=3, window_s=60) is None  # the window moved on


def test_a_demo_clock_jump_back_does_not_lock_anyone_out():
    limiter = RateLimiter()
    for _ in range(3):
        limiter.hit("ip", T0 + timedelta(hours=10), limit=3, window_s=60)
    assert limiter.hit("ip", T0, limit=3, window_s=60) is None  # hits "in the future" are forgotten


def test_clear_forgets_everything():
    limiter = RateLimiter()
    limiter.hit("ip", T0, limit=1, window_s=60)
    limiter.clear()
    assert limiter.hit("ip", T0, limit=1, window_s=60) is None


@pytest.mark.parametrize("raw, clean", [("22cs101", "22CS101"), ("  sample-044 ", "SAMPLE-044"), ("abc", "ABC")])
def test_hostel_id_is_upper_cased(raw, clean):
    assert clean_hostel_id(raw) == clean


@pytest.mark.parametrize("raw", ["ab", "22 CS", "a/b", "x" * 21, "", "<b>"])
def test_bad_hostel_ids(raw):
    with pytest.raises(ApiError) as err:
        clean_hostel_id(raw)
    assert (err.value.status, err.value.code) == (400, "INVALID_HOSTEL_ID")
