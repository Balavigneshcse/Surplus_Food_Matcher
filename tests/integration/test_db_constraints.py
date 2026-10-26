"""The database itself enforces the safety rules: waste hierarchy, one taker per batch, one reserve dish
per meal, one vessel per meal, and the append-only probe log."""
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.db import DbSession
from app.core.errors import constraint_code, install_error_handlers
from app.models import Dish, MealDish, ProbeReading, ReserveBatch, RouteLog
from tests.integration.factories import at, make_base, make_offer

pytestmark = pytest.mark.integration


@pytest.fixture
def base(db):
    return make_base(db)


def route(base, category: str, destination: str, with_batch: bool = True, reason: str | None = None) -> RouteLog:
    return RouteLog(kitchen_id=base.kitchen.id, meal_id=base.meal.id,
                    batch_id=base.batch.id if with_batch else None, category=category, destination=destination,
                    qty_g=4000, reason=reason, logged_at=at(15), logged_by=base.cook.id)


def assert_rejected_by(db, constraint: str) -> IntegrityError:
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    db.rollback()
    assert caught.value.orig.diag.constraint_name == constraint
    return caught.value


# ---------------------------------------------------------------- route_log CHECKs (waste hierarchy)

def test_cooked_food_to_cattle_feed_is_rejected(db, base):
    db.add(route(base, "COOKED_UNSERVED", "CATTLE_FEED", with_batch=False))
    error = assert_rejected_by(db, "ck_cattle_raw_veg_only")
    assert constraint_code(error)[0] == "CATTLE_FEED_RAW_VEG_ONLY"


def test_raw_vegetable_trimmings_to_cattle_feed_is_accepted(db, base):
    db.add(route(base, "RAW_VEG_TRIMMINGS", "CATTLE_FEED", with_batch=False))
    db.commit()
    assert db.scalar(select(func.count()).select_from(RouteLog)) == 1


@pytest.mark.parametrize("category, destination", [
    ("PLATE_WASTE", "NGO"),             # serving-line or plate food never goes to an NGO
    ("RESERVE_UNCLAIMED", "NGO"),
    ("RESERVE_DONATED", "BIOGAS"),      # a donated reserve always goes to the NGO
])
def test_only_the_donated_reserve_goes_to_an_ngo(db, base, category, destination):
    db.add(route(base, category, destination))
    assert_rejected_by(db, "ck_ngo_only_donated")


def test_reserve_categories_need_a_batch(db, base):
    db.add(route(base, "RESERVE_UNSAFE", "BIOGAS", with_batch=False))
    assert_rejected_by(db, "ck_reserve_has_batch")


def test_landfill_needs_a_reason(db, base):
    db.add(route(base, "PLATE_WASTE", "LANDFILL", with_batch=False))
    assert_rejected_by(db, "ck_landfill_reason")
    db.add(route(base, "PLATE_WASTE", "LANDFILL", with_batch=False, reason="Biogas plant closed today"))
    db.commit()


def test_allowed_routes_are_accepted(db, base):
    db.add_all([route(base, "RESERVE_DONATED", "NGO"), route(base, "RESERVE_UNSAFE", "COMPOST"),
                route(base, "COOKED_UNSERVED", "BIOGAS", with_batch=False)])
    db.commit()
    assert db.scalar(select(func.count()).select_from(RouteLog)) == 3


def test_api_answers_409_with_the_rule_code(base):
    """A real IntegrityError from Postgres becomes a problem+json 409 with the mapped code."""
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/bad-route")
    def bad_route(db: DbSession):
        db.add(route(base, "COOKED_UNSERVED", "CATTLE_FEED", with_batch=False))
        db.commit()

    res = TestClient(app).post("/bad-route")
    assert res.status_code == 409
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["code"] == "CATTLE_FEED_RAW_VEG_ONLY"


# ---------------------------------------------------------------- offer partial unique indexes

def test_only_one_pending_offer_per_batch(db, base):
    make_offer(db, base.batch, base.ngo_a, seq=0)
    db.flush()
    make_offer(db, base.batch, base.ngo_b, seq=1)
    error = assert_rejected_by(db, "ux_offer_one_pending")
    assert constraint_code(error)[0] == "OFFER_ALREADY_PENDING"


def test_a_declined_offer_does_not_block_the_next_one(db, base):
    make_offer(db, base.batch, base.ngo_a, seq=0, status="DECLINED")
    make_offer(db, base.batch, base.ngo_b, seq=1, status="PENDING")
    db.commit()


@pytest.mark.parametrize("second_status", ["ACCEPTED", "COLLECTED", "NO_SHOW"])
def test_only_one_taker_per_batch(db, base, second_status):
    make_offer(db, base.batch, base.ngo_a, seq=0, status="ACCEPTED")
    db.flush()
    make_offer(db, base.batch, base.ngo_b, seq=1, status=second_status)
    error = assert_rejected_by(db, "ux_offer_one_taker")
    assert constraint_code(error)[0] == "OFFER_NOT_OPEN"


def test_an_ngo_is_offered_a_batch_only_once(db, base):
    make_offer(db, base.batch, base.ngo_a, seq=0, status="DECLINED")
    db.flush()
    make_offer(db, base.batch, base.ngo_a, seq=1, status="PENDING")
    assert_rejected_by(db, "uq_offer_batch_ngo")


# ---------------------------------------------------------------- one reserve dish, one vessel per meal

def test_one_reserve_dish_per_meal(db, base):
    base.sambhar_line.is_reserve = True  # rice is already the reserve dish
    error = assert_rejected_by(db, "ux_meal_one_reserve")
    assert constraint_code(error)[0] == "ONE_RESERVE_DISH"


def test_many_non_reserve_dishes_are_fine(db, base):
    poriyal = Dish(kitchen_id=base.kitchen.id, name="Poriyal", cooked_g_per_diner=80)
    db.add(poriyal)
    db.flush()
    db.add(MealDish(meal_id=base.meal.id, dish_id=poriyal.id, is_reserve=False, cooked_g_per_diner=80))
    db.commit()
    reserve_rows = db.scalars(select(MealDish).where(MealDish.meal_id == base.meal.id, MealDish.is_reserve)).all()
    assert len(reserve_rows) == 1


def test_one_vessel_per_meal(db, base):
    db.add(ReserveBatch(meal_id=base.meal.id, meal_dish_id=base.rice_line.id, batch_no="TEST1-20261030-L2",
                        food_name="Rice", is_veg=True, planned_g=1000, prepared_at=at(12), lidded_at=at(12)))
    assert_rejected_by(db, "uq_reserve_batch_meal")


# ---------------------------------------------------------------- probe_reading is append-only

def add_reading(db, base) -> ProbeReading:
    reading = ProbeReading(batch_id=base.batch.id, temp_c=Decimal("72.5"), read_at=at(11, 45), kind="LID",
                           recorded_by=base.cook.id)
    db.add(reading)
    db.commit()
    return reading


def test_probe_readings_cannot_be_updated(db, base):
    reading = add_reading(db, base)
    with pytest.raises(DBAPIError, match="probe_reading is append-only"):
        db.execute(text("update probe_reading set temp_c = 80 where id = :id"), {"id": reading.id})
    db.rollback()


def test_probe_readings_cannot_be_deleted(db, base):
    reading = add_reading(db, base)
    with pytest.raises(DBAPIError, match="probe_reading is append-only"):
        db.execute(text("delete from probe_reading where id = :id"), {"id": reading.id})
    db.rollback()
    assert db.scalar(select(func.count()).select_from(ProbeReading)) == 1


def test_orm_edit_of_a_reading_is_blocked_too(db, base):
    reading = add_reading(db, base)
    reading.note = "changed later"
    with pytest.raises(DBAPIError, match="probe_reading is append-only"):
        db.flush()
    db.rollback()


def test_truncate_still_works_for_demo_reset(db, base):
    add_reading(db, base)
    db.execute(text("truncate probe_reading"))
    db.commit()
    assert db.scalar(select(func.count()).select_from(ProbeReading)) == 0


@pytest.mark.parametrize("temp", ["-10.5", "120.5"])
def test_probe_temperature_range(db, base, temp):
    db.add(ProbeReading(batch_id=base.batch.id, temp_c=Decimal(temp), read_at=at(12), kind="ROUTINE",
                        recorded_by=base.cook.id))
    assert_rejected_by(db, "ck_probe_temp_range")
