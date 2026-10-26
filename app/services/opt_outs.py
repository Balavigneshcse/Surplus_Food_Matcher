"""Student opt-outs. (Opt-out and cancel commands arrive with the PREDICT phase.)

Privacy (DPDP): opt-out rows are deleted 30 days after the meal closes; the counts stay on the meal.
"""
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.planning import Meal, MealSlot, OptOut
from app.schemas.common import MealStatus


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
