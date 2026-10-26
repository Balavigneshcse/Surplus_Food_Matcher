"""The injectable clock: aware IST times, the IST date, and swapping the clock for every dependency."""
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.clock import IST, Clock, ClockDep, get_clock, use_clock


class FixedClock(Clock):
    def __init__(self, at: datetime):
        self.at = at

    def now(self) -> datetime:
        return self.at


def test_now_is_timezone_aware_ist():
    now = Clock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(hours=5, minutes=30)


def test_today_is_the_ist_date_not_the_utc_date():
    # 20:00 UTC on 29 Oct is already 01:30 on 30 Oct in India
    clock = FixedClock(datetime(2026, 10, 29, 20, 0, tzinfo=timezone.utc).astimezone(IST))
    assert clock.today().isoformat() == "2026-10-30"


def test_use_clock_changes_the_clock_every_endpoint_gets():
    app = FastAPI()

    @app.get("/now")
    def now(clock: ClockDep) -> dict:
        return {"now": clock.now().isoformat()}

    previous = get_clock()
    use_clock(FixedClock(datetime(2026, 10, 30, 8, 30, tzinfo=IST)))
    try:
        assert TestClient(app).get("/now").json() == {"now": "2026-10-30T08:30:00+05:30"}
    finally:
        use_clock(previous)
    assert get_clock() is previous
