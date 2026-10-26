"""Scheduler steps 1-2 (plan 8.6) against the database: issue at the cutoff, then start service.
Tests call loop_tick(now=...) directly (APP_SCHEDULER_ENABLED=false), or move the demo clock."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.clock import get_clock, use_clock
from app.core.security import CurrentUser
from app.demo.clock import DemoClock
from app.models import Meal, MealDish
from app.scheduler import loop_tick
from app.schemas.planning import MealCreateIn
from app.services import meals
from tests.integration.factories import DAY, add_opt_outs, at, make_planning

pytestmark = pytest.mark.integration


@pytest.fixture
def setup(db):
    return make_planning(db)


def cook(setup) -> CurrentUser:
    return CurrentUser(id=setup.cook.id, role="KITCHEN", kitchen_id=setup.kitchen.id, ngo_id=None)


def new_meal(db, setup, slot=None, now=None) -> int:
    body = MealCreateIn(slot_id=(slot or setup.lunch).id, date=DAY,
                        dishes=[{"dish_id": setup.rice.id, "is_reserve": True}, {"dish_id": setup.sambhar.id}])
    return meals.create_meal(db, cook(setup), body, now or at(7, 0))


def status(db, meal_id) -> Meal:
    meal = db.get(Meal, meal_id)
    db.refresh(meal)
    return meal


def test_step_1_issues_at_the_cutoff_and_freezes_the_numbers(db, setup):
    meal_id = new_meal(db, setup)
    add_opt_outs(db, setup.kitchen, 45)
    loop_tick(now=at(8, 59))
    assert status(db, meal_id).status == "PLANNED"

    loop_tick(now=at(9, 0))  # 12:00 - 180 min
    meal = status(db, meal_id)
    assert (meal.status, meal.issued_at, meal.p50, meal.p90, meal.opted_out_count) == ("ISSUED", at(9, 0), 812, 861, 45)
    assert (meal.rule_p50, meal.rule_p90, meal.forecast_method) == (812, 861, "RULE_V1")
    rice = db.scalar(select(MealDish).where(MealDish.meal_id == meal_id, MealDish.is_reserve))
    assert (rice.line_g, rice.reserve_g) == (162400, 9800)
    version = meal.version

    loop_tick(now=at(9, 15))  # already issued: nothing changes
    assert status(db, meal_id).version == version


def test_step_1_keeps_a_manual_forecast(db, setup):
    from app.schemas.planning import OverrideIn
    meal_id = new_meal(db, setup)
    meals.override(db, cook(setup), meal_id, OverrideIn(p50=900, p90=990, reason="Hostel day"))
    loop_tick(now=at(9, 0))
    meal = status(db, meal_id)
    assert (meal.status, meal.forecast_method, meal.p50, meal.p90, meal.rule_p50) == ("ISSUED", "MANUAL", 900, 990, 850)


def test_step_2_starts_service_at_the_start_time(db, setup):
    meal_id = new_meal(db, setup)
    loop_tick(now=at(9, 0))
    loop_tick(now=at(11, 59))
    assert status(db, meal_id).status == "ISSUED"
    loop_tick(now=at(12, 0))
    assert status(db, meal_id).status == "IN_SERVICE"


def test_a_late_meal_is_issued_and_started_in_one_tick(db, setup):
    """Steps run in order, so a meal planned after its start time is issued (step 1) and then started (step 2)."""
    meal_id = new_meal(db, setup, now=at(12, 5))
    loop_tick(now=at(12, 10))
    meal = status(db, meal_id)
    assert (meal.status, meal.issued_at) == ("IN_SERVICE", at(12, 10))


def test_only_due_meals_are_found(db, setup):
    lunch = new_meal(db, setup)
    dinner = new_meal(db, setup, slot=setup.dinner)  # cutoff 16:30
    assert meals.find_past_cutoff(db, at(9, 0)) == [lunch]
    assert meals.find_past_cutoff(db, at(16, 30)) == [lunch, dinner]
    assert meals.find_past_start(db, at(12, 0)) == []  # nothing ISSUED yet
    meals.auto_issue(db, lunch, at(9, 0))
    assert meals.find_past_start(db, at(11, 59)) == []
    assert meals.find_past_start(db, at(12, 0)) == [lunch]


def test_handlers_recheck_the_state(db, setup):
    meal_id = new_meal(db, setup)
    meals.auto_issue(db, meal_id, at(8, 0))  # before the cutoff: does nothing
    assert status(db, meal_id).status == "PLANNED"
    meals.start_service(db, meal_id, at(12, 30))  # not issued yet: does nothing
    assert status(db, meal_id).status == "PLANNED"
    meals.issue_cook_card(db, cook(setup), meal_id, at(8, 45))  # the manager was first
    meals.auto_issue(db, meal_id, at(9, 0))
    assert status(db, meal_id).issued_at == at(8, 45)
    meals.auto_issue(db, 99999, at(9, 0))  # a meal that vanished (demo reset) is skipped


def test_the_tick_uses_the_demo_clock(db, setup):
    meal_id = new_meal(db, setup)
    previous = get_clock()
    clock = DemoClock()
    use_clock(clock)
    try:
        clock.set(datetime(2026, 10, 30, 8, 55))
        loop_tick()
        assert status(db, meal_id).status == "PLANNED"
        clock.jump(5)  # 09:00
        loop_tick()
        meal = status(db, meal_id)
        assert meal.status == "ISSUED"
        assert abs(meal.issued_at - at(9, 0)) < timedelta(seconds=5)
        clock.set(datetime(2026, 10, 30, 12, 0))
        loop_tick()
        assert status(db, meal_id).status == "IN_SERVICE"
    finally:
        use_clock(previous)
