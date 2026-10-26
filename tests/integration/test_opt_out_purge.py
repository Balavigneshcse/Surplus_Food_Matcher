"""Privacy: opt-out rows are deleted 30 days after the meal closes (the nightly job)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Meal, OptOut
from app.services.opt_outs import purge_old
from tests.integration.factories import DAY, at, make_base

pytestmark = pytest.mark.integration


def add_closed_meal(db, base, day, closed_at):
    meal = Meal(kitchen_id=base.kitchen.id, meal_slot_id=base.slot.id, meal_date=day,
                service_start_at=at(12, day=day), service_end_at=at(14, day=day), status="CLOSED",
                registered_count=1000, attendance_ratio=Decimal("0.850"), buffer_pct=Decimal("6.0"),
                actual_diners=800, closed_at=closed_at, created_by=base.cook.id)
    db.add(meal)
    for n in range(3):
        db.add(OptOut(kitchen_id=base.kitchen.id, slot="LUNCH", meal_date=day, hostel_id=f"H-{day:%m%d}-{n}"))
    db.commit()


def test_only_opt_outs_of_meals_closed_over_30_days_ago_are_deleted(db):
    base = make_base(db)
    now = at(2, 30)
    old_day, recent_day = DAY - timedelta(days=40), DAY - timedelta(days=5)
    add_closed_meal(db, base, old_day, closed_at=at(15, day=old_day))
    add_closed_meal(db, base, recent_day, closed_at=at(15, day=recent_day))
    db.add(OptOut(kitchen_id=base.kitchen.id, slot="LUNCH", meal_date=DAY, hostel_id="TODAY-1"))  # meal still open
    db.commit()

    assert purge_old(db, now, retention_days=30) == 3

    remaining = set(db.scalars(select(OptOut.meal_date)))
    assert remaining == {recent_day, DAY}
    assert db.scalar(select(func.count()).select_from(OptOut)) == 4
