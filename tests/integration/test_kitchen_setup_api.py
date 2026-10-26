"""Kitchen setup over HTTP: meal slots (GET, PUT) and dishes (GET, POST, PUT)."""
import pytest

from app.models import MealSlot
from tests.integration.factories import log_in, make_ngo, make_planning

pytestmark = pytest.mark.integration


@pytest.fixture
def setup(db):
    return make_planning(db)


@pytest.fixture
def csrf(client, setup, clock):
    return log_in(client, "cook")


def slot_body(**overrides):
    body = {"serviceStart": "12:30", "serviceEnd": "14:30", "optoutCutoffMin": 120, "attendanceRatio": 0.8,
            "bufferPct": 7.5, "shareArrivedByT90": 0.45, "standingNgoId": None, "pickupOffsetMin": 20,
            "rescueEnabled": True}
    return body | overrides


def test_list_slots_with_kitchen_info_and_partner_options(client, csrf, setup, db):
    make_ngo(db, "Not a partner")  # no MoU with this kitchen: never offered as a partner
    db.commit()
    res = client.get("/api/kitchen/slots")
    assert res.status_code == 200
    data = res.json()
    assert data["kitchen"] == {"id": setup.kitchen.id, "code": "TEST1", "name": "Test Kitchen TEST1",
                               "registeredDiners": 1000, "sideDishBasis": "P50_TOPUP"}
    assert [s["slot"] for s in data["slots"]] == ["LUNCH", "DINNER"]
    lunch = data["slots"][0]
    assert lunch == {"id": setup.lunch.id, "slot": "LUNCH", "serviceStart": "12:00:00", "serviceEnd": "14:00:00",
                     "optoutCutoffMin": 180, "attendanceRatio": 0.85, "bufferPct": 6.0, "shareArrivedByT90": 0.4,
                     "standingNgoId": setup.partner.id, "standingNgoName": "Partner of TEST1",
                     "pickupOffsetMin": 15, "rescueEnabled": True}
    assert data["partners"] == [{"id": setup.partner.id, "name": "Partner of TEST1"}]


def test_update_slot(client, csrf, setup, db):
    res = client.put(f"/api/kitchen/slots/{setup.lunch.id}", json=slot_body(standingNgoId=setup.partner.id),
                     headers={"X-CSRF-Token": csrf})
    assert res.status_code == 200, res.text
    assert res.json()["attendanceRatio"] == 0.8 and res.json()["serviceStart"] == "12:30:00"
    slot = db.get(MealSlot, setup.lunch.id)
    db.refresh(slot)
    assert (str(slot.attendance_ratio), str(slot.buffer_pct), slot.optout_cutoff_min) == ("0.800", "7.5", 120)


@pytest.mark.parametrize("overrides", [
    {"serviceEnd": "12:00"},  # end before start
    {"attendanceRatio": 1.2},
    {"attendanceRatio": 0.8555},  # more than 3 decimals
    {"shareArrivedByT90": 0},  # a divisor: must be above 0
    {"bufferPct": -1},
    {"optoutCutoffMin": -5},
])
def test_update_slot_rejects_bad_values(client, csrf, setup, overrides):
    res = client.put(f"/api/kitchen/slots/{setup.lunch.id}", json=slot_body(**overrides),
                     headers={"X-CSRF-Token": csrf})
    assert (res.status_code, res.json()["code"]) == (400, "VALIDATION_FAILED")


def test_standing_partner_must_have_an_mou(client, csrf, setup, db):
    stranger = make_ngo(db, "No MoU NGO")
    db.commit()
    res = client.put(f"/api/kitchen/slots/{setup.lunch.id}", json=slot_body(standingNgoId=stranger.id),
                     headers={"X-CSRF-Token": csrf})
    assert (res.status_code, res.json()["code"]) == (409, "NOT_A_PARTNER")


def test_dishes_list_create_update(client, csrf, setup):
    names = [d["name"] for d in client.get("/api/kitchen/dishes").json()]
    assert names == ["Chicken curry", "Poriyal", "Rice", "Sambhar"]

    new = {"name": "  Curd rice ", "nameTa": "தயிர் சாதம்", "isVeg": True, "cookedGPerDiner": 180,
           "rawGPerDiner": 60, "costPerKgInr": 55.5}
    res = client.post("/api/kitchen/dishes", json=new, headers={"X-CSRF-Token": csrf})
    assert res.status_code == 201, res.text
    dish = res.json()
    assert dish | {"id": 0} == {"id": 0, "name": "Curd rice", "nameTa": "தயிர் சாதம்", "isVeg": True,
                                "cookedGPerDiner": 180, "rawGPerDiner": 60, "costPerKgInr": 55.5, "active": True}

    dup = client.post("/api/kitchen/dishes", json=new, headers={"X-CSRF-Token": csrf})
    assert (dup.status_code, dup.json()["code"]) == (409, "DISH_NAME_TAKEN")

    res = client.put(f"/api/kitchen/dishes/{dish['id']}",
                     json=new | {"cookedGPerDiner": 190, "rawGPerDiner": None, "active": False, "nameTa": ""},
                     headers={"X-CSRF-Token": csrf})
    assert res.status_code == 200
    assert (res.json()["cookedGPerDiner"], res.json()["rawGPerDiner"], res.json()["active"],
            res.json()["nameTa"]) == (190, None, False, None)


@pytest.mark.parametrize("bad", [
    {"name": "   "}, {"cookedGPerDiner": 0}, {"rawGPerDiner": -5}, {"costPerKgInr": -1}, {"name": "x" * 101},
])
def test_dish_validation(client, csrf, setup, bad):
    body = {"name": "Kesari", "cookedGPerDiner": 60} | bad
    res = client.post("/api/kitchen/dishes", json=body, headers={"X-CSRF-Token": csrf})
    assert (res.status_code, res.json()["code"]) == (400, "VALIDATION_FAILED")


def test_setup_needs_the_kitchen_role(client, setup, db, clock):
    from tests.integration.factories import make_user
    make_user(db, "ngo1", "NGO", ngo_id=setup.partner.id)
    db.commit()
    assert client.get("/api/kitchen/slots").status_code == 401
    log_in(client, "ngo1")
    assert client.get("/api/kitchen/slots").json()["code"] == "FORBIDDEN"


def test_the_reserve_dish_of_an_open_meal_cannot_become_non_veg(client, csrf, setup, db):
    """Plan 8.2: the reserve vessel is veg in the MVP. A planned meal copies the menu, so turning its reserve
    dish non-veg in setup would slip a non-veg reserve past the menu check."""
    from app.models import Meal
    from tests.integration.factories import DAY
    menu = [{"dishId": setup.rice.id, "isReserve": True}, {"dishId": setup.sambhar.id}]
    res = client.post("/api/kitchen/meals", json={"slotId": setup.lunch.id, "date": DAY.isoformat(), "dishes": menu},
                      headers={"X-CSRF-Token": csrf})
    assert res.status_code == 201, res.text
    meal_id = res.json()["id"]
    rice = {"name": "Rice", "isVeg": False, "cookedGPerDiner": 200, "rawGPerDiner": 82}
    res = client.put(f"/api/kitchen/dishes/{setup.rice.id}", json=rice, headers={"X-CSRF-Token": csrf})
    assert (res.status_code, res.json()["code"]) == (409, "RESERVE_MUST_BE_VEG")
    # a side dish of the same meal may change; so may the reserve dish once its meal is closed
    sambhar = {"name": "Sambhar", "isVeg": False, "cookedGPerDiner": 150}
    assert client.put(f"/api/kitchen/dishes/{setup.sambhar.id}", json=sambhar,
                      headers={"X-CSRF-Token": csrf}).status_code == 200
    meal = db.get(Meal, meal_id)
    meal.status, meal.actual_diners = "CLOSED", 800
    db.commit()
    res = client.put(f"/api/kitchen/dishes/{setup.rice.id}", json=rice, headers={"X-CSRF-Token": csrf})
    assert (res.status_code, res.json()["isVeg"]) == (200, False)
