"""Demo clock and demo reset: ADMIN only, and only included when APP_DEMO=true."""
from fastapi import APIRouter, Depends
from pydantic import Field, model_validator

from app.core.clock import get_clock
from app.core.db import DbSession
from app.core.errors import ApiError
from app.core.security import admin_user, csrf_protect
from app.demo.clock import DemoClock
from app.demo.seeder import reset_demo
from app.schemas.common import ApiModel, IstDateTime

router = APIRouter(prefix="/api/admin/demo", tags=["demo"],
                   dependencies=[Depends(admin_user), Depends(csrf_protect)])


class DemoClockIn(ApiModel):
    """Send either `at` (set the time; no offset means IST) or `plusMinutes` (jump)."""
    at: IstDateTime | None = None
    plus_minutes: int | None = Field(default=None, ge=-1440, le=1440)

    @model_validator(mode="after")
    def exactly_one(self) -> "DemoClockIn":
        if (self.at is None) == (self.plus_minutes is None):
            raise ValueError("Send either at or plusMinutes")
        return self


class DemoClockOut(ApiModel):
    server_now: IstDateTime
    offset_minutes: int


class DemoResetOut(ApiModel):
    server_now: IstDateTime
    message: str


def _demo_clock() -> DemoClock:
    clock = get_clock()
    if not isinstance(clock, DemoClock):
        raise ApiError(409, "NOT_DEMO_MODE", "The demo clock is only available in demo mode")
    return clock


def _clock_view(clock: DemoClock) -> DemoClockOut:
    return DemoClockOut(server_now=clock.now(), offset_minutes=int(clock.offset.total_seconds() / 60))


@router.get("/clock")
def read_clock() -> DemoClockOut:
    return _clock_view(_demo_clock())


@router.post("/clock")
def set_clock(body: DemoClockIn) -> DemoClockOut:
    clock = _demo_clock()
    if body.at is not None:
        clock.set(body.at)
    else:
        clock.jump(body.plus_minutes)
    return _clock_view(clock)


@router.delete("/clock")
def reset_clock() -> DemoClockOut:
    clock = _demo_clock()
    clock.reset()
    return _clock_view(clock)


@router.post("/reset")
def reset(db: DbSession) -> DemoResetOut:
    clock = _demo_clock()
    reset_demo(db, clock)
    return DemoResetOut(server_now=clock.now(),
                        message="Sample data reset. The demo clock is at 08:30 today.")
