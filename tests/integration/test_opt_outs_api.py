"""Public opt-outs over HTTP (no login): open meals, opt out, undo, cutoff 409, duplicates, hostel ID format,
per-IP rate limit, and the counts reaching the forecast."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import OptOut
from app.services import meals
from tests.integration.factories import DAY, at, log_in, make_planning

pytestmark = pytest.mark.integration


@pytest.fixture
def setup(db):
    return make_planning(db)


@pytest.fixture
def csrf(client, setup, clock):
    """An anonymous student's CSRF token (the page calls /api/auth/csrf when it loads)."""
    return client.get("/api/auth/csrf").json()["csrfToken"]


def body(hostel_id="22CS101", day=DAY, slot="LUNCH", code="TEST1"):
    return {"kitchenCode": code, "date": day.isoformat(), "slot": slot, "hostelId": hostel_id}


def opt_out(client, csrf, **kwargs):
    return client.post("/api/public/opt-outs", json=body(**kwargs), headers={"X-CSRF-Token": csrf})


def undo(client, csrf, **kwargs):
    return client.post("/api/public/opt-outs/cancel", json=body(**kwargs), headers={"X-CSRF-Token": csrf})


def rows(db) -> int:
    return db.scalar(select(func.count()).select_from(OptOut))


# ---------------------------------------------------------------- open meals

def test_open_meals_lists_today_and_tomorrow_before_the_cutoff(client, setup, clock):
    res = client.get("/api/public/kitchens/TEST1/open-meals")
    assert res.status_code == 200
    data = res.json()
    assert (data["kitchenCode"], data["kitchenName"], data["serverNow"]) == (
        "TEST1", "Test Kitchen TEST1", "2026-10-30T08:30:00+05:30")
    assert [(m["date"], m["slot"], m["cutoffAt"]) for m in data["meals"]] == [
        ("2026-10-30", "LUNCH", "2026-10-30T09:00:00+05:30"),
        ("2026-10-30", "DINNER", "2026-10-30T16:30:00+05:30"),
        ("2026-10-31", "LUNCH", "2026-10-31T09:00:00+05:30"),
        ("2026-10-31", "DINNER", "2026-10-31T16:30:00+05:30"),
    ]
    clock.at = at(9, 0)  # the cutoff itself is closed
    slots = [(m["date"], m["slot"]) for m in client.get("/api/public/kitchens/test1/open-meals").json()["meals"]]
    assert ("2026-10-30", "LUNCH") not in slots and ("2026-10-30", "DINNER") in slots


def test_open_meals_unknown_kitchen_is_404(client, setup, clock):
    res = client.get("/api/public/kitchens/NOPE/open-meals")
    assert (res.status_code, res.json()["code"]) == (404, "NOT_FOUND")


def test_an_issued_meal_is_no_longer_open(client, setup, clock, db):
    meal_id = meals.create_meal(db, _cook(setup), _create_body(setup), clock.at)
    meals.issue_cook_card(db, _cook(setup), meal_id, clock.at)
    slots = [(m["date"], m["slot"]) for m in client.get("/api/public/kitchens/TEST1/open-meals").json()["meals"]]
    assert ("2026-10-30", "LUNCH") not in slots


# ---------------------------------------------------------------- opt out, duplicate, undo

def test_opt_out_then_duplicate_then_undo(client, csrf, db, setup):
    res = opt_out(client, csrf)
    assert res.status_code == 200, res.text
    assert res.json() == {
        "kitchenCode": "TEST1", "date": "2026-10-30", "slot": "LUNCH", "optedOut": True,
        "cutoffAt": "2026-10-30T09:00:00+05:30", "serverNow": "2026-10-30T08:30:00+05:30"}
    again = opt_out(client, csrf, hostel_id=" 22cs101 ")  # same student: spaces and case don't matter
    assert again.status_code == 200 and again.json() == res.json()  # harmless, and the same answer
    assert rows(db) == 1
    assert db.scalar(select(OptOut.hostel_id)) == "22CS101"

    res = undo(client, csrf)
    assert res.status_code == 200 and res.json()["optedOut"] is False
    assert rows(db) == 0
    assert undo(client, csrf).json() == res.json()  # undoing twice is harmless, and the same answer


def test_answers_never_reveal_what_another_student_did(client, csrf, db, setup):
    """Anyone can type any hostel ID, so the answer must not depend on that ID's earlier opt-out: otherwise
    'opt out' (already out -> nothing changes) would show who skipped a meal without leaving a trace."""
    assert opt_out(client, csrf, hostel_id="22CS101").status_code == 200  # student A opts out
    probe_known = opt_out(client, csrf, hostel_id="22CS101")  # someone else types A's ID
    probe_new = opt_out(client, csrf, hostel_id="22CS999")  # and an ID that had not opted out
    assert probe_known.status_code == probe_new.status_code == 200
    assert probe_known.json() == probe_new.json()  # identical bodies
    assert set(probe_known.json()) == {"kitchenCode", "date", "slot", "optedOut", "cutoffAt", "serverNow"}
    undo_known = undo(client, csrf, hostel_id="22CS101")
    undo_unknown = undo(client, csrf, hostel_id="22CS555")  # never opted out
    assert undo_known.json() == undo_unknown.json()
    assert "22CS" not in client.get("/api/public/kitchens/TEST1/open-meals").text


def test_opt_out_needs_csrf_but_no_login(client, setup, clock):
    res = client.post("/api/public/opt-outs", json=body())
    assert (res.status_code, res.json()["code"]) == (403, "CSRF_INVALID")


def test_opt_outs_reach_the_live_forecast(client, csrf, db, setup, monkeypatch):
    monkeypatch.setattr(get_settings(), "optout_rate_limit", 100)  # 45 students, but one test client IP
    meal_id = meals.create_meal(db, _cook(setup), _create_body(setup), at(8, 30))
    for n in range(45):
        assert opt_out(client, csrf, hostel_id=f"STU-{n:03d}").status_code == 200
    token = log_in(client, "cook")
    assert token
    view = client.get(f"/api/kitchen/meals/{meal_id}").json()
    assert (view["optOutRows"], view["forecast"]["p50"], view["forecast"]["p90"]) == (45, 812, 861)


# ---------------------------------------------------------------- closed: cutoff, issued, dates

def test_after_the_cutoff_opt_out_and_undo_get_409(client, csrf, setup, clock, db):
    assert opt_out(client, csrf).status_code == 200
    clock.at = at(9, 0)
    for res in (opt_out(client, csrf, hostel_id="22CS102"), undo(client, csrf)):
        assert (res.status_code, res.json()["code"]) == (409, "OPTOUT_CLOSED")
    assert rows(db) == 1


def test_after_the_card_is_issued_opt_outs_are_closed_even_before_the_cutoff(client, csrf, setup, clock, db):
    meal_id = meals.create_meal(db, _cook(setup), _create_body(setup), clock.at)
    meals.issue_cook_card(db, _cook(setup), meal_id, clock.at)
    res = opt_out(client, csrf)
    assert (res.status_code, res.json()["code"]) == (409, "OPTOUT_CLOSED")


def test_dates_outside_today_and_tomorrow(client, csrf, setup):
    res = opt_out(client, csrf, day=DAY - timedelta(days=1))
    assert (res.status_code, res.json()["code"]) == (409, "OPTOUT_CLOSED")
    res = opt_out(client, csrf, day=DAY + timedelta(days=2))
    assert (res.status_code, res.json()["code"]) == (409, "OPTOUT_NOT_OPEN_YET")
    assert opt_out(client, csrf, day=DAY + timedelta(days=1)).status_code == 200


def test_unknown_kitchen_or_slot_is_404(client, csrf, setup):
    res = opt_out(client, csrf, code="NOPE")
    assert (res.status_code, res.json()["code"]) == (404, "NOT_FOUND")
    res = opt_out(client, csrf, slot="BREAKFAST")  # the test kitchen serves no breakfast
    assert (res.status_code, res.json()["code"]) == (404, "NOT_FOUND")
    assert opt_out(client, csrf, slot="SUPPER").status_code == 400


@pytest.mark.parametrize("hostel_id", ["ab", "22 CS 101", "<script>", "22CS101;drop", "x" * 21, "தமிழ்123"])
def test_invalid_hostel_id_is_400(client, csrf, setup, db, hostel_id):
    res = opt_out(client, csrf, hostel_id=hostel_id)
    assert (res.status_code, res.json()["code"]) == (400, "INVALID_HOSTEL_ID")
    assert rows(db) == 0


def test_empty_hostel_id_is_a_validation_error(client, csrf, setup):
    res = opt_out(client, csrf, hostel_id="")
    assert (res.status_code, res.json()["code"]) == (400, "VALIDATION_FAILED")


# ---------------------------------------------------------------- per-IP rate limit

def test_rate_limit_per_ip_answers_429_then_recovers(client, csrf, setup, clock, monkeypatch):
    monkeypatch.setattr(get_settings(), "optout_rate_limit", 3)
    monkeypatch.setattr(get_settings(), "optout_rate_window_s", 60)
    assert opt_out(client, csrf, hostel_id="A-001").status_code == 200
    assert undo(client, csrf, hostel_id="A-001").status_code == 200  # undo counts too
    assert opt_out(client, csrf, hostel_id="bad id").status_code == 400  # so do invalid tries
    res = opt_out(client, csrf, hostel_id="A-002")
    assert (res.status_code, res.json()["code"]) == (429, "TOO_MANY_REQUESTS")
    assert 1 <= int(res.headers["Retry-After"]) <= 60
    clock.at = clock.at + timedelta(seconds=61)
    assert opt_out(client, csrf, hostel_id="A-002").status_code == 200


# ---------------------------------------------------------------- helpers

def _cook(setup):
    from app.core.security import CurrentUser
    return CurrentUser(id=setup.cook.id, role="KITCHEN", kitchen_id=setup.kitchen.id, ngo_id=None)


def _create_body(setup):
    from app.schemas.planning import MealCreateIn
    return MealCreateIn(slot_id=setup.lunch.id, date=DAY,
                        dishes=[{"dish_id": setup.rice.id, "is_reserve": True}, {"dish_id": setup.sambhar.id}])
