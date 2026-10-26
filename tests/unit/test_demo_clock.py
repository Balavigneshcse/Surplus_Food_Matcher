"""DemoClock: set (naive = IST), jump and reset."""
from datetime import datetime, timedelta

from app.core.clock import IST
from app.demo.clock import DemoClock


def test_set_naive_time_means_ist():
    clock = DemoClock()
    clock.set(datetime(2026, 10, 30, 8, 30))
    now = clock.now()
    assert now.tzinfo is not None
    assert now.astimezone(IST).strftime("%Y-%m-%d %H:%M") == "2026-10-30 08:30"
    assert clock.today().isoformat() == "2026-10-30"


def test_jump_moves_forward_and_reset_returns_to_real_time():
    clock = DemoClock()
    clock.jump(15)
    assert clock.offset == timedelta(minutes=15)
    clock.jump(-5)
    assert clock.offset == timedelta(minutes=10)
    clock.reset()
    assert clock.offset == timedelta(0)
