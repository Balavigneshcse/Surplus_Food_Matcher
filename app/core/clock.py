"""The one injectable clock. Business code calls get_clock().now(), never datetime.now()."""
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends

IST = ZoneInfo("Asia/Kolkata")


class Clock:
    def now(self) -> datetime:
        """Timezone-aware current time in Asia/Kolkata."""
        return datetime.now(IST)

    def today(self) -> date:
        """Today's IST date (meal dates always use this, never the UTC date)."""
        return self.now().date()


_clock: Clock = Clock()


def use_clock(c: Clock) -> None:
    """main.py calls use_clock(DemoClock()) when APP_DEMO=true."""
    global _clock
    _clock = c


def get_clock() -> Clock:
    """FastAPI dependency; the scheduler calls it too."""
    return _clock


ClockDep = Annotated[Clock, Depends(get_clock)]
