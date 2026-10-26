"""Student opt-outs: open meals, opt out, undo, the counts the forecast uses, and the nightly purge.

- Opt-outs are stored by kitchen + slot + date (not by meal), so students can opt out before the manager
  plans the menu. The identity is a hostel ID only (DPDP), with a format check and a per-IP rate limit.
- A slot-date is open for opt-outs (and undo) on today and tomorrow, until its cutoff
  (service start - optout_cutoff_min), and only while its meal (if planned already) is still PLANNED:
  once the cook card is issued the numbers are frozen, so later requests get 409 OPTOUT_CLOSED.
- Privacy: opt-out rows are deleted 30 days after the meal closes; the counts stay on the meal.
"""
import math
import re
import threading
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import IST
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import Kitchen, Meal, MealSlot, OptOut
from app.schemas.common import MealStatus
from app.schemas.planning import OpenMeal, OpenMealsOut, OptOutIn, OptOutResult
from app.services.kitchen_setup import SLOT_ORDER


# ---------------------------------------------------------------- rate limit (in memory, one worker)

class RateLimiter:
    """At most `limit` requests per `window_s` seconds for each key (the client IP).

    It lives in memory, which is fine with the one uvicorn worker the app always runs (plan 2.2).
    Times come from the app clock; hits outside [now - window, now] are forgotten, so a demo clock
    jump in either direction never locks anyone out."""

    def __init__(self) -> None:
        self._hits: dict[str, list[datetime]] = {}
        self._lock = threading.Lock()  # plain def endpoints run in a thread pool

    def hit(self, key: str, now: datetime, limit: int, window_s: int) -> int | None:
        """Record one request. Returns None if allowed, else the seconds to wait before trying again."""
        start = now - timedelta(seconds=window_s)
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if start < t <= now]
            if len(recent) >= limit:
                self._hits[key] = recent
                wait = (min(recent) + timedelta(seconds=window_s) - now).total_seconds()
                return max(1, math.ceil(wait))
            recent.append(now)
            self._hits[key] = recent
            if len(self._hits) > 10_000:  # forget idle clients so the dict cannot grow forever
                self._hits = {k: v for k, v in self._hits.items() if v and max(v) > start}
            return None

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()


def check_rate_limit(client_ip: str, now: datetime) -> None:
    s = get_settings()
    wait = rate_limiter.hit(client_ip, now, s.optout_rate_limit, s.optout_rate_window_s)
    if wait is not None:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Too many tries from this network. Wait a minute and try again.",
                       headers={"Retry-After": str(wait)})


# ---------------------------------------------------------------- lookups

def count_for(db: Session, kitchen_id: int, slot: str, day: date) -> int:
    """How many students opted out of this slot-date (the forecast adds the meal's extra_opt_outs)."""
    return db.scalar(select(func.count()).select_from(OptOut).where(
        OptOut.kitchen_id == kitchen_id, OptOut.slot == slot, OptOut.meal_date == day))


def clean_hostel_id(raw: str) -> str:
    """Upper-case and check the format (letters, digits and '-', 3-20 characters by default)."""
    hostel_id = raw.strip().upper()
    if not re.fullmatch(get_settings().hostel_id_pattern, hostel_id):
        raise ApiError(400, "INVALID_HOSTEL_ID", "Enter your hostel ID: letters, digits and '-' only")
    return hostel_id


def _kitchen_by_code(db: Session, code: str) -> Kitchen:
    kitchen = db.scalar(select(Kitchen).where(Kitchen.code == code.strip().upper(), Kitchen.active))
    if kitchen is None:
        raise ApiError(404, "NOT_FOUND", "Kitchen not found. Check the link.")
    return kitchen


def _slot(db: Session, kitchen: Kitchen, slot: str) -> MealSlot:
    row = db.scalar(select(MealSlot).where(MealSlot.kitchen_id == kitchen.id, MealSlot.slot == slot))
    if row is None:
        raise ApiError(404, "NOT_FOUND", "This kitchen does not serve that meal")
    return row


def _meal(db: Session, kitchen_id: int, slot: MealSlot, day: date, lock: bool = False) -> Meal | None:
    """The planned meal of this slot-date, if any. lock=True takes a shared lock on its row until commit
    (SELECT ... FOR SHARE): issuing the card locks the same row, so an opt-out is either counted in the
    frozen numbers or refused, never lost in between (see meals.lock_meal_row)."""
    stmt = select(Meal).where(Meal.kitchen_id == kitchen_id, Meal.meal_slot_id == slot.id, Meal.meal_date == day)
    if lock:
        stmt = stmt.with_for_update(read=True).execution_options(populate_existing=True)
    return db.scalar(stmt)


def _cutoff(slot: MealSlot, day: date, meal: Meal | None) -> datetime:
    """Opt-outs close optout_cutoff_min before service starts (the cook card is printed before cooking)."""
    start = meal.service_start_at if meal is not None else datetime.combine(day, slot.service_start, IST)
    return start - timedelta(minutes=slot.optout_cutoff_min)


def _is_open(slot: MealSlot, day: date, meal: Meal | None, now: datetime) -> bool:
    return now < _cutoff(slot, day, meal) and (meal is None or meal.status == MealStatus.PLANNED)


def _today(now: datetime) -> date:
    return now.astimezone(IST).date()


# ---------------------------------------------------------------- public API

def open_meals(db: Session, kitchen_code: str, now: datetime) -> OpenMealsOut:
    """Slot-dates of today and tomorrow that still take opt-outs, earliest first."""
    kitchen = _kitchen_by_code(db, kitchen_code)
    slots = sorted(db.scalars(select(MealSlot).where(MealSlot.kitchen_id == kitchen.id)),
                   key=lambda s: SLOT_ORDER.get(s.slot, 9))
    today = _today(now)
    meals = []
    for day in (today, today + timedelta(days=1)):
        for slot in slots:
            meal = _meal(db, kitchen.id, slot, day)
            if _is_open(slot, day, meal, now):
                start = meal.service_start_at if meal else datetime.combine(day, slot.service_start, IST)
                meals.append(OpenMeal(date=day, slot=slot.slot, service_start_at=start,
                                      cutoff_at=_cutoff(slot, day, meal)))
    return OpenMealsOut(kitchen_code=kitchen.code, kitchen_name=kitchen.name, meals=meals,
                        sample_data=get_settings().demo, server_now=now)


def _require_open(db: Session, kitchen: Kitchen, slot: MealSlot, day: date, now: datetime) -> datetime:
    """Return the cutoff, or raise 409 if this slot-date does not take opt-outs (now or yet)."""
    today = _today(now)
    meal = _meal(db, kitchen.id, slot, day, lock=True)  # held until the opt-out (or undo) commits
    if day > today + timedelta(days=1):
        raise ApiError(409, "OPTOUT_NOT_OPEN_YET", "Opt-outs open the day before the meal")
    if day < today or not _is_open(slot, day, meal, now):
        raise ApiError(409, "OPTOUT_CLOSED", "Opt-outs for this meal are closed: the cook card is ready")
    return _cutoff(slot, day, meal)


def opt_out(db: Session, body: OptOutIn, client_ip: str, now: datetime) -> OptOutResult:
    """Record an opt-out. Repeating it is harmless, and the answer is the same either way (privacy)."""
    check_rate_limit(client_ip, now)
    hostel_id = clean_hostel_id(body.hostel_id)
    kitchen = _kitchen_by_code(db, body.kitchen_code)
    slot = _slot(db, kitchen, body.slot)
    cutoff = _require_open(db, kitchen, slot, body.date, now)
    found = db.scalar(select(OptOut.id).where(OptOut.kitchen_id == kitchen.id, OptOut.slot == slot.slot,
                                              OptOut.meal_date == body.date, OptOut.hostel_id == hostel_id))
    if found is None:
        db.add(OptOut(kitchen_id=kitchen.id, slot=slot.slot, meal_date=body.date, hostel_id=hostel_id,
                      created_at=now))
        try:
            db.commit()
        except IntegrityError:  # the same student tapped twice at the same moment: already opted out
            db.rollback()
    return OptOutResult(kitchen_code=kitchen.code, date=body.date, slot=slot.slot, opted_out=True,
                        cutoff_at=cutoff, server_now=now)


def cancel(db: Session, body: OptOutIn, client_ip: str, now: datetime) -> OptOutResult:
    """Undo an opt-out before the cutoff. Undoing one that does not exist is harmless, and the answer is the
    same either way (privacy)."""
    check_rate_limit(client_ip, now)
    hostel_id = clean_hostel_id(body.hostel_id)
    kitchen = _kitchen_by_code(db, body.kitchen_code)
    slot = _slot(db, kitchen, body.slot)
    cutoff = _require_open(db, kitchen, slot, body.date, now)
    db.execute(delete(OptOut).where(OptOut.kitchen_id == kitchen.id, OptOut.slot == slot.slot,
                                    OptOut.meal_date == body.date, OptOut.hostel_id == hostel_id))
    db.commit()
    return OptOutResult(kitchen_code=kitchen.code, date=body.date, slot=slot.slot, opted_out=False,
                        cutoff_at=cutoff, server_now=now)


# ---------------------------------------------------------------- privacy: nightly purge

def purge_old(db: Session, now: datetime, retention_days: int) -> int:
    """Delete opt-outs of meals that closed more than `retention_days` ago. Returns rows deleted."""
    cutoff = now - timedelta(days=retention_days)
    closed_long_ago = (
        select(Meal.id)
        .join(MealSlot, MealSlot.id == Meal.meal_slot_id)
        .where(Meal.kitchen_id == OptOut.kitchen_id, MealSlot.slot == OptOut.slot,
               Meal.meal_date == OptOut.meal_date, Meal.status == MealStatus.CLOSED,
               Meal.closed_at < cutoff)
        .correlate(OptOut)
    )
    result = db.execute(delete(OptOut).where(closed_long_ago.exists())
                        .execution_options(synchronize_session=False))
    db.commit()
    return result.rowcount
