"""DemoClock: the rules never change for a demo; we jump the clock instead (demo mode only)."""
from datetime import datetime, timedelta

from app.core.clock import IST, Clock


class DemoClock(Clock):
    def __init__(self) -> None:
        self.offset = timedelta(0)

    def now(self) -> datetime:
        return datetime.now(IST) + self.offset

    def set(self, at: datetime) -> None:
        if at.tzinfo is None:  # a time with no offset means IST
            at = at.replace(tzinfo=IST)
        self.offset = at - datetime.now(IST)

    def jump(self, minutes: int) -> None:
        self.offset += timedelta(minutes=minutes)

    def reset(self) -> None:
        self.offset = timedelta(0)
