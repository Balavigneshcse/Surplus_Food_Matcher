"""The demo seeder is idempotent, uses today's IST date, and demo reset works despite the probe trigger."""
import re
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.clock import IST, Clock
from app.core.config import get_settings
from app.core.security import password_hash
from app.demo.clock import DemoClock
from app.demo.seeder import reset_demo, seed_demo
from app.models import (AppUser, Dish, Kitchen, Meal, MealDish, MealSlot, Ngo, OptOut, Partnership, ProbeReading,
                        ReserveBatch)

pytestmark = pytest.mark.integration

EXPECTED_COUNTS = {Kitchen: 1, Ngo: 4, Partnership: 4, AppUser: 3, MealSlot: 2, Dish: 3, Meal: 2, MealDish: 5,
                   OptOut: 44, ReserveBatch: 1, ProbeReading: 3}


@pytest.fixture(autouse=True)
def demo_passwords(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_admin_password", "admin-test-pass")
    monkeypatch.setattr(settings, "demo_kitchen_password", "kitchen-test-pass")
    monkeypatch.setattr(settings, "demo_ngo_password", "ngo-test-pass")


def counts(db) -> dict:
    return {model: db.scalar(select(func.count()).select_from(model)) for model in EXPECTED_COUNTS}


def test_seed_creates_the_sample_data_once(db):
    clock = Clock()
    seed_demo(db, clock)
    assert counts(db) == EXPECTED_COUNTS
    seed_demo(db, clock)  # second run changes nothing
    assert counts(db) == EXPECTED_COUNTS


def test_seeded_kitchen_slots_and_users(db):
    seed_demo(db, Clock())
    kitchen = db.scalar(select(Kitchen))
    assert (kitchen.code, kitchen.name, kitchen.registered_diners) == ("MESS1", "Sample Hostel Mess", 1000)
    lunch = db.scalar(select(MealSlot).where(MealSlot.slot == "LUNCH"))
    dinner = db.scalar(select(MealSlot).where(MealSlot.slot == "DINNER"))
    assert (lunch.service_start, lunch.service_end) == (time(12, 0), time(14, 0))
    assert lunch.rescue_enabled is True and dinner.rescue_enabled is False
    assert all(ngo.name.startswith("Sample NGO") for ngo in db.scalars(select(Ngo)))
    assert [n.has_reheating for n in db.scalars(select(Ngo).order_by(Ngo.name))] == [True, True, True, False]
    kitchen_user = db.scalar(select(AppUser).where(AppUser.username == "kitchen"))
    assert kitchen_user.role == "KITCHEN" and kitchen_user.kitchen_id == kitchen.id
    assert password_hash.verify("kitchen-test-pass", kitchen_user.password_hash)


def test_todays_lunch_uses_the_ist_date_and_has_one_reserve_dish(db):
    clock = DemoClock()
    clock.set(datetime(2026, 10, 30, 8, 30))
    seed_demo(db, clock)
    lunch = db.scalar(select(Meal).join(MealSlot).where(MealSlot.slot == "LUNCH"))
    assert lunch.meal_date.isoformat() == "2026-10-30"
    assert lunch.status == "PLANNED"
    assert lunch.service_start_at.astimezone(IST).strftime("%H:%M") == "12:00"
    reserve = db.scalars(select(MealDish).where(MealDish.meal_id == lunch.id, MealDish.is_reserve)).all()
    assert len(reserve) == 1
    opt_outs = db.scalar(select(func.count()).select_from(OptOut).where(OptOut.meal_date == lunch.meal_date))
    assert opt_outs == 44


def test_just_after_midnight_the_seeder_uses_the_ist_date_not_the_utc_date(db):
    clock = DemoClock()
    clock.set(datetime(2026, 10, 30, 0, 30))  # 00:30 IST = 19:00 UTC on 29 Oct
    assert clock.now().astimezone(timezone.utc).date() == date(2026, 10, 29)
    seed_demo(db, clock)
    lunch = db.scalar(select(Meal).join(MealSlot).where(MealSlot.slot == "LUNCH"))
    dinner = db.scalar(select(Meal).join(MealSlot).where(MealSlot.slot == "DINNER"))
    assert lunch.meal_date == date(2026, 10, 30)  # today in IST
    assert dinner.meal_date == date(2026, 10, 29)  # yesterday in IST
    assert set(db.scalars(select(OptOut.meal_date))) == {date(2026, 10, 30)}
    assert db.scalar(select(ReserveBatch.batch_no)) == "MESS1-20261029-D"


def test_everything_seeded_is_labelled_as_sample_data(db):
    seed_demo(db, Clock())
    kitchen = db.scalar(select(Kitchen))
    assert kitchen.name == "Sample Hostel Mess" and "sample data" in kitchen.address
    for ngo in db.scalars(select(Ngo)):
        assert ngo.name.startswith("Sample NGO ") and "(sample data)" in ngo.address
        assert ngo.contact_phone is None  # no phone numbers, real or fake
        assert re.fullmatch(r"[0-9]{14}", ngo.fssai_reg_no)  # fake, but in the right format
    assert {ngo.name for ngo in db.scalars(select(Ngo))} == {f"Sample NGO {k}" for k in "ABCD"}
    assert all(u.display_name.startswith("Sample ") for u in db.scalars(select(AppUser)))
    assert all(p.mou_ref.startswith("MOU-SAMPLE-") for p in db.scalars(select(Partnership)))
    assert set(db.scalars(select(OptOut.hostel_id).limit(3))) <= {f"SAMPLE-{n:03d}" for n in range(1, 45)}


def test_yesterdays_dinner_batch_is_red_and_waiting_to_be_routed(db):
    clock = DemoClock()
    clock.set(datetime(2026, 10, 30, 8, 30))
    seed_demo(db, clock)
    batch = db.scalar(select(ReserveBatch))
    assert batch.batch_no == "MESS1-20261029-D"
    assert (batch.status, batch.worst_colour, batch.planned_g) == ("TO_DISPOSE", "RED", 6000)
    last_reading = max(r.read_at for r in batch.readings)
    assert clock.now() - last_reading > timedelta(hours=4)


def test_skips_users_without_a_password(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_kitchen_password", None)
    seed_demo(db, Clock())
    assert db.scalar(select(AppUser).where(AppUser.username == "kitchen")) is None
    assert db.scalar(select(func.count()).select_from(Meal)) == 0  # meals need the kitchen user


def test_reset_truncates_and_reseeds_and_sets_the_clock(db):
    clock = DemoClock()
    seed_demo(db, clock)
    db.add(OptOut(kitchen_id=db.scalar(select(Kitchen.id)), slot="LUNCH", meal_date=clock.today(),
                  hostel_id="EXTRA-1"))
    db.commit()
    reset_demo(db, clock)  # TRUNCATE works even though the trigger blocks DELETE on probe_reading
    assert counts(db) == EXPECTED_COUNTS
    assert sorted(db.scalars(select(Meal.id))) == [1, 2]  # RESTART IDENTITY: the sample meals are #1 and #2 again
    assert db.scalar(select(func.count()).select_from(Kitchen)) == 1  # orgs and users are kept, not duplicated
    now = clock.now().astimezone(IST)
    assert now.strftime("%H:%M") == "08:30"
    assert now.date() == datetime.now(IST).date()
