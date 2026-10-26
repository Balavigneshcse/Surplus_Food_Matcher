"""Meals over HTTP: create from slot defaults, live forecast, edit only while PLANNED, override with a reason,
issue freezes the numbers, live door count."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Dish, Meal, MealDish, MealSlot
from tests.integration.factories import DAY, add_opt_outs, at, log_in, make_planning

pytestmark = pytest.mark.integration


@pytest.fixture
def setup(db):
    return make_planning(db)


@pytest.fixture
def csrf(client, setup, clock):
    return log_in(client, "cook")


def menu(setup, usual_rice=185000):
    return [{"dishId": setup.rice.id, "isReserve": True, "usualG": usual_rice},
            {"dishId": setup.sambhar.id, "isReserve": False, "usualG": 135000},
            {"dishId": setup.poriyal.id, "isReserve": False}]


def create(client, csrf, setup, **overrides):
    body = {"slotId": setup.lunch.id, "date": DAY.isoformat(), "dishes": menu(setup), **overrides}
    return client.post("/api/kitchen/meals", json=body, headers={"X-CSRF-Token": csrf})


def post(client, csrf, path, body=None):
    return client.post(path, json=body, headers={"X-CSRF-Token": csrf})


def card(view, name):
    return next(line for line in view["cookCard"] if line["name"] == name)


# ---------------------------------------------------------------- create

def test_create_meal_from_slot_defaults(client, csrf, setup):
    res = create(client, csrf, setup)
    assert res.status_code == 201, res.text
    view = res.json()
    assert (view["slot"], view["date"], view["status"]) == ("LUNCH", "2026-10-30", "PLANNED")
    assert view["registeredCount"] == 1000  # the kitchen's registered diners
    assert view["serviceStartAt"] == "2026-10-30T12:00:00+05:30"
    assert view["cutoffAt"] == "2026-10-30T09:00:00+05:30"
    assert view["optoutOpen"] is True
    assert (view["attendanceRatio"], view["bufferPct"]) == (0.85, 6.0)
    assert view["forecast"] == {"p50": 850, "p90": 901, "method": "RULE_V1", "ruleP50": 850, "ruleP90": 901,
                                "overrideReason": None, "frozen": False}
    assert view["serverNow"] == "2026-10-30T08:30:00+05:30"
    assert [line["name"] for line in view["cookCard"]] == ["Rice", "Sambhar", "Poriyal"]  # reserve dish first
    rice = card(view, "Rice")
    assert (rice["isReserve"], rice["usualG"], rice["nameTa"]) == (True, 185000, "சாதம்")
    assert view["reserveG"] == 51 * 200


def test_create_takes_registered_count_and_extra_opt_outs(client, csrf, setup):
    view = create(client, csrf, setup, registeredCount=1100, extraOptOuts=145).json()
    assert (view["registeredCount"], view["extraOptOuts"], view["optedOut"], view["eligible"]) == (1100, 145, 145, 955)
    assert (view["forecast"]["p50"], view["forecast"]["p90"]) == (812, 861)


@pytest.mark.parametrize("dishes, code", [
    ("no_reserve", "ONE_RESERVE_DISH"),
    ("two_reserves", "ONE_RESERVE_DISH"),
    ("non_veg_reserve", "RESERVE_MUST_BE_VEG"),
])
def test_menu_needs_exactly_one_veg_reserve_dish(client, csrf, setup, dishes, code):
    menus = {
        "no_reserve": [{"dishId": setup.rice.id}, {"dishId": setup.sambhar.id}],
        "two_reserves": [{"dishId": setup.rice.id, "isReserve": True},
                         {"dishId": setup.sambhar.id, "isReserve": True}],
        "non_veg_reserve": [{"dishId": setup.chicken.id, "isReserve": True}, {"dishId": setup.rice.id}],
    }
    res = create(client, csrf, setup, dishes=menus[dishes])
    assert res.status_code == 409
    assert res.json()["code"] == code


def test_create_rejects_bad_menus_and_dates(client, csrf, setup, db):
    twice = [{"dishId": setup.rice.id, "isReserve": True}, {"dishId": setup.rice.id}]
    assert create(client, csrf, setup, dishes=twice).json()["code"] == "DISH_ALREADY_ON_MENU"
    assert create(client, csrf, setup, dishes=[]).status_code == 400
    missing = create(client, csrf, setup, dishes=[{"dishId": 99999, "isReserve": True}])
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
    setup.poriyal.active = False
    db.commit()
    inactive = create(client, csrf, setup, dishes=menu(setup))
    assert (inactive.status_code, inactive.json()["code"]) == (409, "DISH_INACTIVE")
    past = create(client, csrf, setup, date="2026-10-29", dishes=menu(setup)[:2])
    assert (past.status_code, past.json()["code"]) == (409, "MEAL_DATE_PAST")
    assert create(client, csrf, setup, dishes=menu(setup)[:2]).status_code == 201
    again = create(client, csrf, setup, dishes=menu(setup)[:2])
    assert (again.status_code, again.json()["code"]) == (409, "MEAL_EXISTS")


def test_create_needs_csrf(client, csrf, setup):
    res = client.post("/api/kitchen/meals", json={"slotId": setup.lunch.id, "date": DAY.isoformat(),
                                                  "dishes": menu(setup)})
    assert (res.status_code, res.json()["code"]) == (403, "CSRF_INVALID")


# ---------------------------------------------------------------- live forecast (PLANNED)

def test_forecast_and_cook_card_update_live_as_opt_outs_arrive(client, csrf, setup, db):
    meal_id = create(client, csrf, setup).json()["id"]
    add_opt_outs(db, setup.kitchen, 44)
    view = client.get(f"/api/kitchen/meals/{meal_id}").json()
    assert (view["optOutRows"], view["optedOut"], view["eligible"]) == (44, 44, 956)
    assert (view["forecast"]["p50"], view["forecast"]["p90"]) == (813, 862)
    assert card(view, "Rice")["lineG"] == 162600

    add_opt_outs(db, setup.kitchen, 1, prefix="LATE")
    view = client.get(f"/api/kitchen/meals/{meal_id}").json()
    assert (view["forecast"]["p50"], view["forecast"]["p90"]) == (812, 861)
    rice, sambhar = card(view, "Rice"), card(view, "Sambhar")
    # plan 8.2: rice 70.6 kg raw -> serving line 162.4 kg + RESERVE VESSEL 9.8 kg; sambhar 121.8 kg + top-up 7.4 kg
    assert (rice["rawG"], rice["lineG"], rice["reserveG"], rice["topUpG"]) == (70602, 162400, 9800, 0)
    assert (sambhar["rawG"], sambhar["lineG"], sambhar["reserveG"], sambhar["topUpG"]) == (None, 121800, 0, 7350)
    assert (rice["plannedG"], sambhar["plannedG"]) == (172200, 121800)
    assert view["reserveG"] == 9800
    assert view["sideDishBasis"] == "P50_TOPUP"


def test_planned_meal_follows_the_slot_ratio_and_the_kitchen_side_dish_basis(client, csrf, setup, db):
    meal_id = create(client, csrf, setup).json()["id"]
    setup.lunch.attendance_ratio = Decimal("0.800")
    setup.kitchen.side_dish_basis = "P90"
    db.commit()
    view = client.get(f"/api/kitchen/meals/{meal_id}").json()
    assert (view["forecast"]["p50"], view["forecast"]["p90"]) == (800, 848)
    assert view["sideDishBasis"] == "P90"
    assert (card(view, "Sambhar")["lineG"], card(view, "Sambhar")["topUpG"]) == (848 * 150, 0)


def test_list_meals_by_date(client, csrf, setup):
    create(client, csrf, setup)
    create(client, csrf, setup, slotId=setup.dinner.id, dishes=menu(setup)[:2])
    res = client.get("/api/kitchen/meals", params={"date": DAY.isoformat()})
    assert res.status_code == 200
    body = res.json()
    assert [(m["slot"], m["status"], m["p50"], m["p90"]) for m in body["meals"]] == [
        ("LUNCH", "PLANNED", 850, 901), ("DINNER", "PLANNED", 500, 530)]
    assert body["meals"][0]["reserveG"] == 51 * 200
    assert client.get("/api/kitchen/meals").json()["date"] == "2026-10-30"  # default: today (IST)
    assert client.get("/api/kitchen/meals", params={"date": "2026-10-31"}).json()["meals"] == []


# ---------------------------------------------------------------- edit (PLANNED only)

def test_edit_counts_and_menu_while_planned(client, csrf, setup, db):
    created = create(client, csrf, setup).json()
    new_menu = [{"dishId": setup.sambhar.id, "isReserve": False, "usualG": 140000},
                {"dishId": setup.rice.id, "isReserve": True, "usualG": 180000}]
    res = client.put(f"/api/kitchen/meals/{created['id']}",
                     json={"registeredCount": 1000, "extraOptOuts": 45, "dishes": new_menu,
                           "version": created["version"]},
                     headers={"X-CSRF-Token": csrf})
    assert res.status_code == 200, res.text
    view = res.json()
    assert (view["forecast"]["p50"], view["forecast"]["p90"]) == (812, 861)
    assert [line["name"] for line in view["cookCard"]] == ["Rice", "Sambhar"]
    assert card(view, "Sambhar")["usualG"] == 140000
    assert view["version"] == created["version"] + 1
    assert len(db.scalars(select(MealDish).where(MealDish.meal_id == created["id"])).all()) == 2

    stale = client.put(f"/api/kitchen/meals/{created['id']}",
                       json={"registeredCount": 900, "dishes": new_menu, "version": created["version"]},
                       headers={"X-CSRF-Token": csrf})
    assert (stale.status_code, stale.json()["code"]) == (409, "CONCURRENT_EDIT")
    bad = client.put(f"/api/kitchen/meals/{created['id']}",
                     json={"registeredCount": 900, "dishes": [{"dishId": setup.sambhar.id}]},
                     headers={"X-CSRF-Token": csrf})
    assert (bad.status_code, bad.json()["code"]) == (409, "ONE_RESERVE_DISH")


def test_issued_meal_cannot_be_edited_or_overridden(client, csrf, setup):
    meal_id = create(client, csrf, setup).json()["id"]
    assert post(client, csrf, f"/api/kitchen/meals/{meal_id}/issue-cook-card").status_code == 200
    res = client.put(f"/api/kitchen/meals/{meal_id}", json={"registeredCount": 900, "dishes": menu(setup)},
                     headers={"X-CSRF-Token": csrf})
    assert (res.status_code, res.json()["code"]) == (409, "MEAL_NOT_PLANNED")
    res = post(client, csrf, f"/api/kitchen/meals/{meal_id}/override", {"p50": 900, "p90": 950, "reason": "Fest"})
    assert (res.status_code, res.json()["code"]) == (409, "MEAL_NOT_PLANNED")
    res = post(client, csrf, f"/api/kitchen/meals/{meal_id}/issue-cook-card")
    assert (res.status_code, res.json()["code"]) == (409, "MEAL_NOT_PLANNED")


# ---------------------------------------------------------------- override (MANUAL)

def test_override_needs_a_reason_and_p90_at_least_p50(client, csrf, setup):
    meal_id = create(client, csrf, setup).json()["id"]
    path = f"/api/kitchen/meals/{meal_id}/override"
    for body in ({"p50": 900, "p90": 950}, {"p50": 900, "p90": 950, "reason": "   "}):
        res = post(client, csrf, path, body)
        assert (res.status_code, res.json()["code"]) == (400, "OVERRIDE_NEEDS_REASON")
    res = post(client, csrf, path, {"p50": 900, "p90": 899, "reason": "Sports day"})
    assert (res.status_code, res.json()["code"]) == (400, "P90_BELOW_P50")
    assert post(client, csrf, path, {"p50": -1, "p90": 10, "reason": "x"}).status_code == 400


def test_override_keeps_the_rule_numbers_and_the_card_uses_the_manual_ones(client, csrf, setup, db):
    meal_id = create(client, csrf, setup).json()["id"]
    res = post(client, csrf, f"/api/kitchen/meals/{meal_id}/override",
               {"p50": 1100, "p90": 1200, "reason": "  Alumni day: 200 guests  "})
    assert res.status_code == 200, res.text
    view = res.json()
    assert view["forecast"] == {"p50": 1100, "p90": 1200, "method": "MANUAL", "ruleP50": 850, "ruleP90": 901,
                                "overrideReason": "Alumni day: 200 guests", "frozen": False}
    assert card(view, "Rice")["reserveG"] == 100 * 200  # events: reserve = (high - expected) x g/diner
    add_opt_outs(db, setup.kitchen, 45)  # opt-outs move the rule numbers, not the manual ones
    view = client.get(f"/api/kitchen/meals/{meal_id}").json()
    assert (view["forecast"]["p50"], view["forecast"]["ruleP50"]) == (1100, 812)
    meal = db.get(Meal, meal_id)
    db.refresh(meal)
    assert (meal.forecast_method, meal.rule_p50, meal.rule_p90) == ("MANUAL", 850, 901)


# ---------------------------------------------------------------- issue (freeze)

def test_issue_freezes_the_numbers(client, csrf, setup, db, clock):
    meal_id = create(client, csrf, setup).json()["id"]
    add_opt_outs(db, setup.kitchen, 45)
    clock.at = at(8, 45)
    res = post(client, csrf, f"/api/kitchen/meals/{meal_id}/issue-cook-card")
    assert res.status_code == 200, res.text
    issued = res.json()
    assert issued["status"] == "ISSUED"
    assert issued["issuedAt"] == "2026-10-30T08:45:00+05:30"
    assert issued["forecast"]["frozen"] is True and issued["optoutOpen"] is False
    assert (issued["forecast"]["p50"], issued["forecast"]["p90"]) == (812, 861)

    meal = db.get(Meal, meal_id)
    db.refresh(meal)
    assert (meal.p50, meal.p90, meal.rule_p50, meal.rule_p90) == (812, 861, 812, 861)
    assert (meal.opted_out_count, meal.attendance_ratio, meal.buffer_pct) == (45, Decimal("0.850"), Decimal("6.0"))
    lines = {md.dish_id: (md.line_g, md.reserve_g) for md in db.scalars(select(MealDish))}
    assert lines[setup.rice.id] == (162400, 9800)
    assert lines[setup.sambhar.id] == (121800, 0)

    # nothing that happens later changes the issued card
    add_opt_outs(db, setup.kitchen, 10, prefix="AFTER")
    db.get(MealSlot, setup.lunch.id).attendance_ratio = Decimal("0.500")
    db.get(Dish, setup.rice.id).cooked_g_per_diner = 250
    setup.kitchen.side_dish_basis = "P90"
    db.commit()
    later = client.get(f"/api/kitchen/meals/{meal_id}").json()
    for key in ("forecast", "cookCard", "optedOut", "eligible", "attendanceRatio", "reserveG", "sideDishBasis"):
        assert later[key] == issued[key], key
    assert card(later, "Sambhar")["topUpG"] == 7350  # still the P50 + top-up card it was issued with


# ---------------------------------------------------------------- live door count

def test_live_count_runs_during_service_only(client, csrf, setup):
    meal_id = create(client, csrf, setup).json()["id"]
    path = f"/api/kitchen/meals/{meal_id}/live-count"
    res = post(client, csrf, path, {"count": 10})
    assert (res.status_code, res.json()["code"]) == (409, "MEAL_NOT_IN_SERVICE")
    post(client, csrf, f"/api/kitchen/meals/{meal_id}/issue-cook-card")

    view = post(client, csrf, path, {"count": 320}).json()
    assert (view["liveCount"], view["liveCountAt"]) == (320, "2026-10-30T08:30:00+05:30")
    assert post(client, csrf, path, {"delta": 1}).json()["liveCount"] == 321
    assert post(client, csrf, path, {"delta": 10}).json()["liveCount"] == 331
    assert post(client, csrf, path, {"delta": -1}).json()["liveCount"] == 330
    res = post(client, csrf, path, {"delta": -331})
    assert (res.status_code, res.json()["code"]) == (409, "COUNT_BELOW_ZERO")
    for body in ({}, {"count": 5, "delta": 1}, {"count": -1}):
        assert post(client, csrf, path, body).status_code == 400
