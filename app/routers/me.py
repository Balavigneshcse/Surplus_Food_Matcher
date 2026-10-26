"""GET /api/me: who is logged in, their kitchen/NGO, the SAMPLE DATA flag and the server time."""
from fastapi import APIRouter, Depends

from app.core.clock import ClockDep
from app.core.config import get_settings
from app.core.db import DbSession
from app.core.security import LoggedInUser, csrf_protect
from app.schemas.org import MeOut
from app.services import users

router = APIRouter(prefix="/api", tags=["me"], dependencies=[Depends(csrf_protect)])


@router.get("/me")
def me(user: LoggedInUser, db: DbSession, clock: ClockDep) -> MeOut:
    return users.me_view(db, user, sample_data=get_settings().demo, now=clock.now())
