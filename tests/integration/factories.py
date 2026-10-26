"""Small helpers that create rows for integration tests (each test makes its own data)."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.core.clock import IST, Clock
from app.core.security import password_hash
from app.models import (AppUser, Dish, Kitchen, Meal, MealDish, MealSlot, Ngo, Offer, OptOut, Partnership,
                        ReserveBatch)

DAY = date(2026, 10, 30)


def at(hour: int, minute: int = 0, day: date = DAY) -> datetime:
    return datetime.combine(day, time(hour, minute), IST)


def make_kitchen(db: Session, code: str = "TEST1") -> Kitchen:
    kitchen = Kitchen(code=code, name=f"Test Kitchen {code}", address="Test address",
                      fssai_licence_no="10000000000099", registered_diners=1000)
    db.add(kitchen)
    db.flush()
    return kitchen


def make_ngo(db: Session, name: str) -> Ngo:
    ngo = Ngo(name=name, address="Test address", fssai_reg_no="20000000000099", capacity_g=30000,
              open_from=time(10, 0), open_to=time(22, 0), has_reheating=True, has_trained_handler=True)
    db.add(ngo)
    db.flush()
    return ngo


def make_user(db: Session, username: str, role: str, password: str = "test-password",
              kitchen_id: int | None = None, ngo_id: int | None = None) -> AppUser:
    user = AppUser(username=username, password_hash=password_hash.hash(password), display_name=username.title(),
                   role=role, kitchen_id=kitchen_id, ngo_id=ngo_id)
    db.add(user)
    db.flush()
    return user


def make_base(db: Session) -> SimpleNamespace:
    """A kitchen with a cook, two NGOs, a lunch slot, two dishes, one meal and its lidded reserve batch."""
    kitchen = make_kitchen(db)
    cook = make_user(db, "cook", "KITCHEN", kitchen_id=kitchen.id)
    ngo_a = make_ngo(db, "Test NGO A")
    ngo_b = make_ngo(db, "Test NGO B")
    slot = MealSlot(kitchen_id=kitchen.id, slot="LUNCH", service_start=time(12, 0), service_end=time(14, 0),
                    standing_ngo_id=ngo_a.id)
    rice = Dish(kitchen_id=kitchen.id, name="Rice", cooked_g_per_diner=200, raw_g_per_diner=82)
    sambhar = Dish(kitchen_id=kitchen.id, name="Sambhar", cooked_g_per_diner=150)
    db.add_all([slot, rice, sambhar])
    db.flush()
    meal = Meal(kitchen_id=kitchen.id, meal_slot_id=slot.id, meal_date=DAY, service_start_at=at(12),
                service_end_at=at(14), registered_count=1000, attendance_ratio=Decimal("0.850"),
                buffer_pct=Decimal("6.0"), created_by=cook.id)
    db.add(meal)
    db.flush()
    rice_line = MealDish(meal_id=meal.id, dish_id=rice.id, is_reserve=True, cooked_g_per_diner=200,
                         raw_g_per_diner=82)
    sambhar_line = MealDish(meal_id=meal.id, dish_id=sambhar.id, is_reserve=False, cooked_g_per_diner=150)
    db.add_all([rice_line, sambhar_line])
    db.flush()
    batch = ReserveBatch(meal_id=meal.id, meal_dish_id=rice_line.id, batch_no="TEST1-20261030-L",
                         food_name="Rice", is_veg=True, planned_g=9800, lidded_weight_g=9800,
                         prepared_at=at(11, 45), lidded_at=at(11, 45))
    db.add(batch)
    db.commit()
    return SimpleNamespace(kitchen=kitchen, cook=cook, ngo_a=ngo_a, ngo_b=ngo_b, slot=slot, rice=rice,
                           sambhar=sambhar, meal=meal, rice_line=rice_line, sambhar_line=sambhar_line, batch=batch)


def make_offer(db: Session, batch: ReserveBatch, ngo: Ngo, seq: int, status: str = "PENDING") -> Offer:
    sent = at(12, 30)
    offer = Offer(batch_id=batch.id, ngo_id=ngo.id, seq=seq, status=status, qty_g=9800, pickup_at=at(14, 15),
                  sent_at=sent, expires_at=sent + timedelta(minutes=10))
    db.add(offer)
    return offer


# ---------------------------------------------------------------- planning (Phase 2)

class FixedClock(Clock):
    """A clock that says what the test tells it to (tests move it by changing `.at`)."""

    def __init__(self, now: datetime) -> None:
        self.at = now

    def now(self) -> datetime:
        return self.at


def make_planning(db: Session, code: str = "TEST1", username: str = "cook") -> SimpleNamespace:
    """A kitchen (1000 registered) with a cook, a partner NGO with an MoU, LUNCH 12:00-14:00 (cutoff 180 min,
    ratio 0.85, buffer 6 %) and DINNER 19:30-21:30, and dishes Rice (200 g / 82 g raw), Sambhar 150 g,
    Poriyal 80 g and a non-veg Chicken curry. No meals yet."""
    kitchen = make_kitchen(db, code)
    cook = make_user(db, username, "KITCHEN", kitchen_id=kitchen.id)
    partner = make_ngo(db, f"Partner of {code}")
    db.add(Partnership(kitchen_id=kitchen.id, ngo_id=partner.id, mou_ref=f"MOU-{code}"))
    lunch = MealSlot(kitchen_id=kitchen.id, slot="LUNCH", service_start=time(12, 0), service_end=time(14, 0),
                     optout_cutoff_min=180, attendance_ratio=Decimal("0.850"), buffer_pct=Decimal("6.0"),
                     standing_ngo_id=partner.id)
    dinner = MealSlot(kitchen_id=kitchen.id, slot="DINNER", service_start=time(19, 30), service_end=time(21, 30),
                      optout_cutoff_min=180, attendance_ratio=Decimal("0.500"), buffer_pct=Decimal("6.0"),
                      rescue_enabled=False)
    rice = Dish(kitchen_id=kitchen.id, name="Rice", name_ta="சாதம்", cooked_g_per_diner=200, raw_g_per_diner=82)
    sambhar = Dish(kitchen_id=kitchen.id, name="Sambhar", cooked_g_per_diner=150)
    poriyal = Dish(kitchen_id=kitchen.id, name="Poriyal", cooked_g_per_diner=80)
    chicken = Dish(kitchen_id=kitchen.id, name="Chicken curry", is_veg=False, cooked_g_per_diner=120)
    db.add_all([lunch, dinner, rice, sambhar, poriyal, chicken])
    db.commit()
    return SimpleNamespace(kitchen=kitchen, cook=cook, partner=partner, lunch=lunch, dinner=dinner, rice=rice,
                           sambhar=sambhar, poriyal=poriyal, chicken=chicken)


def add_opt_outs(db: Session, kitchen: Kitchen, n: int, day: date = DAY, slot: str = "LUNCH",
                 prefix: str = "H") -> None:
    for i in range(1, n + 1):
        db.add(OptOut(kitchen_id=kitchen.id, slot=slot, meal_date=day, hostel_id=f"{prefix}-{i:03d}"))
    db.commit()


def log_in(client, username: str, password: str = "test-password") -> str:
    """Log a TestClient in and return the new CSRF token (send it as X-CSRF-Token)."""
    token = client.get("/api/auth/csrf").json()["csrfToken"]
    res = client.post("/api/auth/login", data={"username": username, "password": password},
                      headers={"X-CSRF-Token": token})
    assert res.status_code == 200, res.text
    return res.json()["csrfToken"]
