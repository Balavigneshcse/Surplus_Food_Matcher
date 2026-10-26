"""Issue vs opt-out at the same moment (plan 8.1): an opt-out is either counted in the frozen numbers or
refused with 409 OPTOUT_CLOSED; it is never accepted and then left out of the card.

Each test holds one transaction open half way and runs the other side in a thread with its own session
(like the offer race test in plan 11.5). The thread must wait for the open transaction: if it finishes at
once, the row lock is missing."""
import threading

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.security import CurrentUser
from app.models import Meal, MealSlot, OptOut
from app.schemas.planning import MealCreateIn, OptOutIn
from app.services import meals, opt_outs
from tests.integration.factories import DAY, at, make_planning

pytestmark = pytest.mark.integration

WAIT_S = 0.5  # a thread that is not blocked finishes well within this


@pytest.fixture
def setup(db):
    return make_planning(db)


def cook(setup) -> CurrentUser:
    return CurrentUser(id=setup.cook.id, role="KITCHEN", kitchen_id=setup.kitchen.id, ngo_id=None)


@pytest.fixture
def meal_id(db, setup) -> int:
    body = MealCreateIn(slot_id=setup.lunch.id, date=DAY,
                        dishes=[{"dish_id": setup.rice.id, "is_reserve": True}, {"dish_id": setup.sambhar.id}])
    return meals.create_meal(db, cook(setup), body, at(8, 0))


def in_thread(fn):
    """Start fn in a thread; returns (thread, result) where result gets 'value' or 'error'."""
    result = {}

    def target():
        try:
            result["value"] = fn()
        except Exception as exc:  # noqa: BLE001 - the test inspects it
            result["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, result


def test_issue_waits_for_an_opt_out_being_saved_and_counts_it(setup, meal_id):
    student = SessionLocal()
    try:
        # an opt-out half way: the open check took its shared lock on the meal row, the row is inserted,
        # nothing is committed yet
        slot = student.get(MealSlot, setup.lunch.id)
        assert opt_outs._meal(student, setup.kitchen.id, slot, DAY, lock=True).status == "PLANNED"
        student.add(OptOut(kitchen_id=setup.kitchen.id, slot="LUNCH", meal_date=DAY, hostel_id="RACE-1",
                           created_at=at(8, 59)))
        student.flush()

        def issue():
            with SessionLocal() as manager:
                meals.issue_cook_card(manager, cook(setup), meal_id, at(8, 59))

        thread, result = in_thread(issue)
        thread.join(WAIT_S)
        blocked = thread.is_alive()
        student.commit()
    finally:
        student.close()
    thread.join(10)
    assert blocked, "issuing did not wait for the opt-out that was being saved"
    assert "error" not in result, result
    with SessionLocal() as db:
        meal = db.get(Meal, meal_id)
        # 1000 - 1 = 999 x 0.85 = 849.15 -> 849; ceil(849 x 1.06) = 900
        assert (meal.status, meal.opted_out_count, meal.p50, meal.p90) == ("ISSUED", 1, 849, 900)


def test_an_opt_out_during_the_issue_waits_and_gets_409(setup, meal_id):
    manager = SessionLocal()
    try:
        # issuing half way: the meal row is locked and already ISSUED, nothing committed yet
        meal = meals.get_meal(manager, cook(setup), meal_id, lock=True)
        meals._issue(manager, meal, at(8, 59))
        manager.flush()

        def student():
            with SessionLocal() as db:
                body = OptOutIn(kitchen_code="TEST1", date=DAY, slot="LUNCH", hostel_id="RACE-2")
                return opt_outs.opt_out(db, body, "10.0.0.2", at(8, 59))

        thread, result = in_thread(student)
        thread.join(WAIT_S)
        blocked = thread.is_alive()
        manager.commit()
    finally:
        manager.close()
    thread.join(10)
    assert blocked, "the opt-out did not wait for the cook card being issued"
    error = result.get("error")
    assert isinstance(error, ApiError) and (error.status, error.code) == (409, "OPTOUT_CLOSED"), result
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(OptOut)) == 0
        assert db.get(Meal, meal_id).opted_out_count == 0


def test_the_scheduler_issue_takes_the_same_lock(setup, meal_id):
    student = SessionLocal()
    try:
        slot = student.get(MealSlot, setup.lunch.id)
        opt_outs._meal(student, setup.kitchen.id, slot, DAY, lock=True)
        student.add(OptOut(kitchen_id=setup.kitchen.id, slot="LUNCH", meal_date=DAY, hostel_id="RACE-3",
                           created_at=at(8, 59)))
        student.flush()

        def tick_step_1():
            with SessionLocal() as db:
                meals.auto_issue(db, meal_id, at(9, 0))

        thread, result = in_thread(tick_step_1)
        thread.join(WAIT_S)
        blocked = thread.is_alive()
        student.commit()
    finally:
        student.close()
    thread.join(10)
    assert blocked, "the scheduler's issue did not wait for the opt-out that was being saved"
    assert "error" not in result, result
    with SessionLocal() as db:
        assert db.get(Meal, meal_id).opted_out_count == 1
