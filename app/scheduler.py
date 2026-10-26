"""The loop tick (every 15 s) and the nightly opt-out purge.

APScheduler starts and stops these in main.py's lifespan. Tests set APP_SCHEDULER_ENABLED=false
and call loop_tick(now=...) directly.
"""
import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.clock import get_clock
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services import opt_outs

log = logging.getLogger(__name__)

FindDue = Callable[[Session, datetime], list[int]]
Handle = Callable[[Session, int, datetime], None]

# (name, find_due(db, now) -> list of ids, handle(db, id, now)); always run in this order.
# Later phases add the steps from plan 8.6: issue-at-cutoff, start-service, t90, expire-offers,
# safeclock, no-show, unclaimed.
STEPS: list[tuple[str, FindDue, Handle]] = []


def loop_tick(now: datetime | None = None) -> None:
    """Run every step. Each item gets its own session + transaction, so one bad row never stops the tick."""
    now = now or get_clock().now()
    for name, find_due, handle in STEPS:
        with SessionLocal() as db:
            ids = find_due(db, now)  # short read
        for item_id in ids:
            try:
                with SessionLocal() as db:
                    handle(db, item_id, now)  # re-checks state with a conditional UPDATE, then commits
            except Exception:
                log.exception("tick step %s failed for id %s", name, item_id)


def purge_old_opt_outs(now: datetime | None = None) -> None:
    """Nightly (02:30 IST): delete opt-out rows of meals closed more than 30 days ago."""
    now = now or get_clock().now()
    try:
        with SessionLocal() as db:
            deleted = opt_outs.purge_old(db, now, get_settings().optout_retention_days)
        log.info("purged %s old opt-out rows", deleted)
    except Exception:
        log.exception("opt-out purge failed")
