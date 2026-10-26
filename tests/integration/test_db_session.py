"""The database session: UTC connections, aware timestamps, no hidden commits, and the optimistic lock."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm.exc import StaleDataError

from app.core.clock import IST
from app.core.db import DbSession, SessionLocal, get_db
from app.core.errors import install_error_handlers
from app.models import Kitchen, Meal, ReserveBatch
from tests.integration.factories import make_base, make_kitchen

pytestmark = pytest.mark.integration


def test_connections_use_utc(db):
    assert db.scalar(text("show timezone")) == "UTC"


def test_an_ist_time_comes_back_as_the_same_instant_in_utc(db):
    lunch_time = datetime(2026, 10, 30, 12, 25, tzinfo=IST)
    kitchen = make_kitchen(db)
    kitchen.created_at = lunch_time
    db.commit()
    kitchen_id = kitchen.id

    with SessionLocal() as fresh:  # read it back through a new session (no cached object)
        stored = fresh.get(Kitchen, kitchen_id).created_at
    assert stored == lunch_time  # the same instant ...
    assert stored.utcoffset() == timedelta(0)  # ... returned as an aware UTC datetime
    assert stored.astimezone(IST).strftime("%H:%M") == "12:25"


def test_get_db_never_commits():
    """Closing the request session without commit() rolls back, so an ApiError undoes every change."""
    dependency = get_db()
    db = next(dependency)
    make_kitchen(db, "NOCOMMIT")  # flushed, not committed
    dependency.close()
    with SessionLocal() as check:
        assert check.scalar(select(func.count()).select_from(Kitchen)) == 0


# ---------------------------------------------------------------- optimistic lock (version column)

@pytest.mark.parametrize("model, field", [(Meal, "live_count"), (ReserveBatch, "lidded_weight_g")])
def test_a_stale_update_loses(db, model, field):
    base = make_base(db)
    row_id = base.meal.id if model is Meal else base.batch.id
    with SessionLocal() as first, SessionLocal() as second:
        mine = first.get(model, row_id)
        theirs = second.get(model, row_id)
        assert mine.version == 1
        setattr(mine, field, 9700)
        first.commit()  # version 1 -> 2
        assert mine.version == 2

        setattr(theirs, field, 9600)  # still thinks the version is 1
        with pytest.raises(StaleDataError):
            second.commit()


def test_a_stale_update_answers_409_concurrent_edit(db):
    base = make_base(db)
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/bump")
    def bump(session: DbSession) -> None:
        meal = session.get(Meal, base.meal.id)
        with SessionLocal() as someone_else:  # another phone saves the same meal first
            someone_else.get(Meal, meal.id).live_count = 300
            someone_else.commit()
        meal.live_count = 320
        session.commit()

    res = TestClient(app).post("/bump")
    assert res.status_code == 409
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["code"] == "CONCURRENT_EDIT"
    with SessionLocal() as check:
        assert check.get(Meal, base.meal.id).live_count == 300  # the first save won
