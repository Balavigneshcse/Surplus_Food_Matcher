"""Kitchen scoping (plan 2.5): kitchen B's user gets 404 on kitchen A's meals, slots and dishes, exactly as if
they did not exist, and lists only ever show the user's own kitchen."""
import pytest

from tests.integration.factories import DAY, log_in, make_planning

pytestmark = pytest.mark.integration


@pytest.fixture
def kitchens(db):
    return make_planning(db, code="KA", username="cook_a"), make_planning(db, code="KB", username="cook_b")


def menu(k):
    return [{"dishId": k.rice.id, "isReserve": True}, {"dishId": k.sambhar.id}]


@pytest.fixture
def meal_a(client, kitchens, clock):
    a, _b = kitchens
    csrf = log_in(client, "cook_a")
    res = client.post("/api/kitchen/meals", json={"slotId": a.lunch.id, "date": DAY.isoformat(), "dishes": menu(a)},
                      headers={"X-CSRF-Token": csrf})
    assert res.status_code == 201
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    return res.json()["id"]


def assert_404(res):
    assert res.status_code == 404, res.text
    assert res.json()["code"] == "NOT_FOUND"


def test_another_kitchens_meal_is_404_for_every_action(client, kitchens, meal_a):
    _a, b = kitchens
    csrf = log_in(client, "cook_b")
    h = {"X-CSRF-Token": csrf}
    assert_404(client.get(f"/api/kitchen/meals/{meal_a}"))
    assert_404(client.put(f"/api/kitchen/meals/{meal_a}", json={"registeredCount": 1, "dishes": menu(b)}, headers=h))
    assert_404(client.post(f"/api/kitchen/meals/{meal_a}/override", json={"p50": 1, "p90": 2, "reason": "x"},
                           headers=h))
    assert_404(client.post(f"/api/kitchen/meals/{meal_a}/issue-cook-card", headers=h))
    assert_404(client.post(f"/api/kitchen/meals/{meal_a}/live-count", json={"delta": 1}, headers=h))
    assert client.get("/api/kitchen/meals", params={"date": DAY.isoformat()}).json()["meals"] == []
    # kitchen A's meal is untouched
    client.post("/api/auth/logout", headers=h)
    log_in(client, "cook_a")
    assert client.get(f"/api/kitchen/meals/{meal_a}").json()["status"] == "PLANNED"


def test_another_kitchens_slot_and_dish_cannot_be_used_or_changed(client, kitchens, clock):
    a, b = kitchens
    csrf = log_in(client, "cook_b")
    h = {"X-CSRF-Token": csrf}
    # a meal on A's slot, or with A's dish, is refused as "not found"
    assert_404(client.post("/api/kitchen/meals", json={"slotId": a.lunch.id, "date": DAY.isoformat(),
                                                       "dishes": menu(b)}, headers=h))
    assert_404(client.post("/api/kitchen/meals", json={"slotId": b.lunch.id, "date": DAY.isoformat(),
                                                       "dishes": menu(a)}, headers=h))
    slot = {"serviceStart": "12:00", "serviceEnd": "14:00", "optoutCutoffMin": 180, "attendanceRatio": 0.85,
            "bufferPct": 6, "shareArrivedByT90": 0.4, "pickupOffsetMin": 15, "rescueEnabled": True}
    assert_404(client.put(f"/api/kitchen/slots/{a.lunch.id}", json=slot, headers=h))
    assert_404(client.put(f"/api/kitchen/dishes/{a.rice.id}", json={"name": "Mine now", "cookedGPerDiner": 1},
                          headers=h))
    # B's own partner list never shows A's partner
    res = client.put(f"/api/kitchen/slots/{b.lunch.id}", json=slot | {"standingNgoId": a.partner.id}, headers=h)
    assert (res.status_code, res.json()["code"]) == (409, "NOT_A_PARTNER")
    data = client.get("/api/kitchen/slots").json()
    assert data["kitchen"]["code"] == "KB"
    assert {s["id"] for s in data["slots"]} == {b.lunch.id, b.dinner.id}
    assert data["partners"] == [{"id": b.partner.id, "name": "Partner of KB"}]
    assert {d["id"] for d in client.get("/api/kitchen/dishes").json()} == {
        b.rice.id, b.sambhar.id, b.poriyal.id, b.chicken.id}
