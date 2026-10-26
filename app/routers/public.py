"""Public endpoints: open meals and opt-outs (CSRF check only; opt-out POSTs are rate-limited per IP).

The hostel ID is always sent in the JSON body, never in the URL.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.core.clock import ClockDep
from app.core.db import DbSession
from app.core.security import csrf_protect
from app.schemas.planning import OpenMealsOut, OptOutIn, OptOutResult
from app.services import opt_outs

router = APIRouter(prefix="/api/public", tags=["public"],
                   dependencies=[Depends(csrf_protect)])


def client_ip(request: Request) -> str:
    # Behind Caddy, uvicorn runs with --proxy-headers, so this is the real client address.
    return request.client.host if request.client else "unknown"


@router.get("/kitchens/{code}/open-meals")
def open_meals(code: Annotated[str, Path(max_length=20)], db: DbSession, clock: ClockDep) -> OpenMealsOut:
    """Slot-dates (today, tomorrow) that still take opt-outs."""
    return opt_outs.open_meals(db, code, clock.now())


@router.post("/opt-outs")
def create_opt_out(body: OptOutIn, request: Request, db: DbSession, clock: ClockDep) -> OptOutResult:
    return opt_outs.opt_out(db, body, client_ip(request), clock.now())


@router.post("/opt-outs/cancel")
def cancel_opt_out(body: OptOutIn, request: Request, db: DbSession, clock: ClockDep) -> OptOutResult:
    return opt_outs.cancel(db, body, client_ip(request), clock.now())
