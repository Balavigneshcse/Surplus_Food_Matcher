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
from app.services import meals, opt_outs

log = logging.getLogger(__name__)

FindDue = Callable[[Session, datetime], list[int]]
Handle = Callable[[Session, int, datetime], None]

# (name, find_due(db, now) -> list of ids, handle(db, id, now)); always run in this order.
# Later phases add the steps from plan 8.6: t90, expire-offers, safeclock, no-show, unclaimed.
STEPS: list[tuple[str, FindDue, Handle]] = [
    ("issue-at-cutoff", meals.find_past_cutoff, meals.auto_issue),  # 1: PLANNED past the cutoff -> ISSUED
    ("start-service", meals.find_past_start, meals.start_service),  # 2: ISSUED past service start -> IN_SERVICE
]


def loop_tick(now: datetime | None = None) -> None:
    """Run every step. Each item gets its own session + transaction, so one bad row never stops the tick."""
    now = now or get_clock().now()
    for name, find_due, handle in STEPS:
        try:
            with SessionLocal() as db:
                ids = find_due(db, now)  # short read
        except Exception:
            log.exception("tick step %s could not find its items", name)
            continue
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
