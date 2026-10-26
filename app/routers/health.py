"""GET /api/health: liveness + database check for deployment. Public, GET only."""
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.clock import ClockDep
from app.core.db import DbSession
from app.core.errors import ApiError
from app.schemas.common import HealthOut

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(db: DbSession, clock: ClockDep) -> HealthOut:
    try:
        db.execute(text("select 1"))
    except SQLAlchemyError:
        raise ApiError(503, "DB_UNAVAILABLE", "The database is not reachable")
    return HealthOut(status="ok", db="ok", server_now=clock.now())
