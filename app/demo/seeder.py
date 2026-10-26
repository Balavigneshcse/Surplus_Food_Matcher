"""Demo seeder (demo mode only). ALL DATA HERE IS SAMPLE DATA: the kitchen and NGOs are fictional.

- Idempotent: rows are looked up by natural key and created only when missing; ids are never set.
- Always uses today's IST date from the clock.
- Passwords come from APP_DEMO_*_PASSWORD and are hashed at runtime with pwdlib.
- reset_demo() empties the transactional tables with TRUNCATE (the probe log trigger blocks DELETE),
  re-seeds, and sets the demo clock to 08:30 today, before the 09:00 opt-out cutoff of lunch.
"""
import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.clock import IST, Clock
from app.core.config import Settings, get_settings
from app.core.security import password_fits_bcrypt, password_hash
from app.demo.clock import DemoClock
from app.models import (AppUser, Dish, Kitchen, Meal, MealDish, MealSlot, Ngo, OptOut, Partnership,
                        ProbeReading, ReserveBatch)
from app.schemas.common import (BatchStatus, Colour, ForecastMethod, MealStatus, ProbeKind, Role, Slot,
                                T90Status)

log = logging.getLogger(__name__)

KITCHEN_CODE = "MESS1"
SAMPLE_OPT_OUTS = 44  # today's lunch: 1000 registered, 44 out -> P50 813 / P90 862 (demo script 0:00)
TRANSACTIONAL_TABLES = ("meal, meal_dish, opt_out, reserve_batch, probe_reading, offer, batch_record,"
                        " route_log")

# Four obviously fictional NGOs with fake 14-digit FSSAI numbers: a partner (A), two more that pass the
# offer filters (B, C) and one with no reheating that fails them (D).
SAMPLE_NGOS = [
    dict(key="A", name="Sample NGO A", fssai_reg_no="20000000000001", capacity_g=30000, min_batch_g=8000,
         has_reheating=True, open_from=time(10, 0), open_to=time(22, 0), lat="11.010000", lng="77.005000"),
    dict(key="B", name="Sample NGO B", fssai_reg_no="20000000000002", capacity_g=20000, min_batch_g=5000,
         has_reheating=True, open_from=time(11, 0), open_to=time(21, 0), lat="11.025000", lng="77.010000"),
    dict(key="C", name="Sample NGO C", fssai_reg_no="20000000000003", capacity_g=15000, min_batch_g=5000,
         has_reheating=True, open_from=time(12, 0), open_to=time(20, 0), lat="11.050000", lng="77.020000"),
    dict(key="D", name="Sample NGO D", fssai_reg_no="20000000000004", capacity_g=25000, min_batch_g=5000,
         has_reheating=False, open_from=time(9, 0), open_to=time(21, 0), lat="11.015000", lng="76.990000"),
]

# (name, Tamil name, cooked g/diner, raw g/diner, Rs per kg)
SAMPLE_DISHES = [
    ("Rice", "சாதம்", 200, 82, "45.00"),
    ("Sambhar", "சாம்பார்", 150, None, "60.00"),
    ("Poriyal", "பொரியல்", 80, None, "80.00"),
]


def seed_demo(db: Session, clock: Clock) -> None:
    now = clock.now()
    today = clock.today()
    settings = get_settings()

    kitchen = _ensure_kitchen(db, now)
    ngos = _ensure_ngos(db, now, today)
    _ensure_partnerships(db, kitchen, ngos)
    users = _ensure_users(db, kitchen, ngos["A"], now, settings)
    slots = _ensure_slots(db, kitchen, ngos["A"])
    dishes = _ensure_dishes(db, kitchen)

    cook = users.get("kitchen")
    if cook is None:
        log.warning("APP_DEMO_KITCHEN_PASSWORD is missing or invalid: sample meals were not created")
    else:
        _ensure_today_lunch(db, kitchen, slots[Slot.LUNCH], dishes, cook, today, now)
        _ensure_yesterday_dinner(db, kitchen, slots[Slot.DINNER], dishes, cook, today - timedelta(days=1), now)
    db.commit()
    log.info("demo data seeded for %s (sample data)", today)


def reset_demo(db: Session, clock: DemoClock) -> None:
    clock.reset()
    db.execute(text(f"TRUNCATE {TRANSACTIONAL_TABLES} RESTART IDENTITY CASCADE"))
    db.execute(update(Ngo).values(pickups_total=0, pickups_on_time=0))  # fresh on-time scores
    db.commit()
    seed_demo(db, clock)
    clock.set(datetime.combine(clock.today(), time(8, 30), IST))


# ---------------------------------------------------------------- organisations and users

def _ensure_kitchen(db: Session, now: datetime) -> Kitchen:
    kitchen = db.scalar(select(Kitchen).where(Kitchen.code == KITCHEN_CODE))
    if kitchen is None:
        kitchen = Kitchen(code=KITCHEN_CODE, name="Sample Hostel Mess",
                          address="Sample campus address, Tamil Nadu (sample data)",
                          fssai_licence_no="10000000000001", registered_diners=1000,
                          default_min_batch_g=8000, max_radius_km=Decimal("15.0"), side_dish_basis="P50_TOPUP",
                          g_per_meal_equiv=420, lat=Decimal("11.000000"), lng=Decimal("77.000000"),
                          active=True, created_at=now)
        db.add(kitchen)
        db.flush()
    return kitchen


def _ensure_ngos(db: Session, now: datetime, today: date) -> dict[str, Ngo]:
    ngos = {}
    for spec in SAMPLE_NGOS:
        ngo = db.scalar(select(Ngo).where(Ngo.name == spec["name"]))
        if ngo is None:
            ngo = Ngo(name=spec["name"], address=f"Sample address {spec['key']} (sample data)",
                      fssai_reg_no=spec["fssai_reg_no"], fssai_verified_at=now,
                      fssai_valid_until=today + timedelta(days=365), accepts_veg=True, accepts_nonveg=False,
                      capacity_g=spec["capacity_g"], min_batch_g=spec["min_batch_g"],
                      has_reheating=spec["has_reheating"], has_trained_handler=True,
                      open_from=spec["open_from"], open_to=spec["open_to"],
                      lat=Decimal(spec["lat"]), lng=Decimal(spec["lng"]),
                      pickups_total=0, pickups_on_time=0, active=True, created_at=now)
            db.add(ngo)
            db.flush()
        ngos[spec["key"]] = ngo
    return ngos


def _ensure_partnerships(db: Session, kitchen: Kitchen, ngos: dict[str, Ngo]) -> None:
    for key, ngo in ngos.items():
        found = db.scalar(select(Partnership).where(Partnership.kitchen_id == kitchen.id,
                                                    Partnership.ngo_id == ngo.id))
        if found is None:
            db.add(Partnership(kitchen_id=kitchen.id, ngo_id=ngo.id, mou_ref=f"MOU-SAMPLE-{key}",
                               mou_valid_until=None, active=True))
    db.flush()


def _ensure_users(db: Session, kitchen: Kitchen, partner: Ngo, now: datetime,
                  settings: Settings) -> dict[str, AppUser]:
    specs = [
        ("admin", "Sample Admin", Role.ADMIN, None, None, settings.demo_admin_password),
        ("kitchen", "Sample Mess Manager", Role.KITCHEN, kitchen.id, None, settings.demo_kitchen_password),
        ("ngo", "Sample NGO A Volunteer", Role.NGO, None, partner.id, settings.demo_ngo_password),
    ]
    users = {}
    for username, display_name, role, kitchen_id, ngo_id, password in specs:
        user = db.scalar(select(AppUser).where(AppUser.username == username))
        if user is None:
            if not _usable_password(password):
                log.warning("demo user %r skipped: set its APP_DEMO_*_PASSWORD (8-64 characters)", username)
                continue
            user = AppUser(username=username, password_hash=password_hash.hash(password),
                           display_name=display_name, role=role, kitchen_id=kitchen_id, ngo_id=ngo_id,
                           enabled=True, created_at=now)
            db.add(user)
            db.flush()
        users[username] = user
    return users


def _usable_password(password: str | None) -> bool:
    return password is not None and 8 <= len(password) <= 64 and password_fits_bcrypt(password)


# ---------------------------------------------------------------- kitchen setup

def _ensure_slots(db: Session, kitchen: Kitchen, partner: Ngo) -> dict[str, MealSlot]:
    specs = [
        # LUNCH 12:00-14:00: cutoff 180 min, ratio 0.85, buffer 6 %, share at T-90 0.40, partner A
        dict(slot=Slot.LUNCH, service_start=time(12, 0), service_end=time(14, 0),
             attendance_ratio=Decimal("0.850"), rescue_enabled=True),
        # DINNER 19:30-21:30 with rescue off (a lower sample ratio: many students eat out at night)
        dict(slot=Slot.DINNER, service_start=time(19, 30), service_end=time(21, 30),
             attendance_ratio=Decimal("0.500"), rescue_enabled=False),
    ]
    slots = {}
    for spec in specs:
        slot = db.scalar(select(MealSlot).where(MealSlot.kitchen_id == kitchen.id,
                                                MealSlot.slot == spec["slot"]))
        if slot is None:
            slot = MealSlot(kitchen_id=kitchen.id, optout_cutoff_min=180, buffer_pct=Decimal("6.0"),
                            share_arrived_by_t90=Decimal("0.400"), standing_ngo_id=partner.id,
                            pickup_offset_min=15, **spec)
            db.add(slot)
            db.flush()
        slots[spec["slot"]] = slot
    return slots


def _ensure_dishes(db: Session, kitchen: Kitchen) -> dict[str, Dish]:
    dishes = {}
    for name, name_ta, cooked_g, raw_g, cost in SAMPLE_DISHES:
        dish = db.scalar(select(Dish).where(Dish.kitchen_id == kitchen.id, Dish.name == name))
        if dish is None:
            dish = Dish(kitchen_id=kitchen.id, name=name, name_ta=name_ta, is_veg=True,
                        cooked_g_per_diner=cooked_g, raw_g_per_diner=raw_g, cost_per_kg_inr=Decimal(cost),
                        active=True)
            db.add(dish)
            db.flush()
        dishes[name] = dish
    return dishes


# ---------------------------------------------------------------- sample meals

def _find_meal(db: Session, kitchen: Kitchen, slot: MealSlot, meal_date: date) -> Meal | None:
    return db.scalar(select(Meal).where(Meal.kitchen_id == kitchen.id, Meal.meal_slot_id == slot.id,
                                        Meal.meal_date == meal_date))


def _at(day: date, clock_time: time) -> datetime:
    return datetime.combine(day, clock_time, IST)


def _add_menu_dish(db: Session, meal: Meal, dish: Dish, is_reserve: bool, usual_g: int,
                   line_g: int | None = None, reserve_g: int | None = None) -> MealDish:
    meal_dish = MealDish(meal_id=meal.id, dish_id=dish.id, is_reserve=is_reserve,
                         cooked_g_per_diner=dish.cooked_g_per_diner, raw_g_per_diner=dish.raw_g_per_diner,
                         line_g=line_g, reserve_g=reserve_g, usual_g=usual_g)
    db.add(meal_dish)
    db.flush()
    return meal_dish


def _ensure_today_lunch(db: Session, kitchen: Kitchen, slot: MealSlot, dishes: dict[str, Dish],
                        cook: AppUser, today: date, now: datetime) -> None:
    """Today's lunch, still PLANNED (the forecast is computed live), with 44 sample opt-outs."""
    if _find_meal(db, kitchen, slot, today) is not None:
        return
    meal = Meal(kitchen_id=kitchen.id, meal_slot_id=slot.id, meal_date=today,
                service_start_at=_at(today, slot.service_start), service_end_at=_at(today, slot.service_end),
                status=MealStatus.PLANNED, registered_count=kitchen.registered_diners, extra_opt_outs=0,
                attendance_ratio=slot.attendance_ratio, buffer_pct=slot.buffer_pct,
                forecast_method=ForecastMethod.RULE_V1, live_count=0, t90_status=T90Status.PENDING,
                created_by=cook.id, created_at=now)
    db.add(meal)
    db.flush()
    # "usual" kg are the kitchen's self-reported amounts before AnnamSetu (cooked grams)
    _add_menu_dish(db, meal, dishes["Rice"], is_reserve=True, usual_g=185000)
    _add_menu_dish(db, meal, dishes["Sambhar"], is_reserve=False, usual_g=135000)
    _add_menu_dish(db, meal, dishes["Poriyal"], is_reserve=False, usual_g=72000)
    for n in range(1, SAMPLE_OPT_OUTS + 1):
        db.add(OptOut(kitchen_id=kitchen.id, slot=slot.slot, meal_date=today, hostel_id=f"SAMPLE-{n:03d}",
                      created_at=now))
    db.flush()


def _ensure_yesterday_dinner(db: Session, kitchen: Kitchen, slot: MealSlot, dishes: dict[str, Dish],
                             cook: AppUser, day: date, now: datetime) -> None:
    """Yesterday's dinner, still in service, whose reserve vessel was last hot more than 4 h ago: RED,
    waiting to be routed (demo script 3:40)."""
    if _find_meal(db, kitchen, slot, day) is not None:
        return
    p50, p90 = 500, 530  # rule forecast: 1000 eligible x 0.500 = 500; ceil(500 x 1.06) = 530
    start, end = _at(day, slot.service_start), _at(day, slot.service_end)
    meal = Meal(kitchen_id=kitchen.id, meal_slot_id=slot.id, meal_date=day, service_start_at=start,
                service_end_at=end, status=MealStatus.IN_SERVICE, registered_count=kitchen.registered_diners,
                extra_opt_outs=0, opted_out_count=0, attendance_ratio=slot.attendance_ratio,
                buffer_pct=slot.buffer_pct, p50=p50, p90=p90, forecast_method=ForecastMethod.RULE_V1,
                rule_p50=p50, rule_p90=p90, issued_at=start - timedelta(minutes=slot.optout_cutoff_min),
                live_count=470, live_count_at=_at(day, time(21, 0)), t90_status=T90Status.SKIPPED,
                t90_reason="Dinner rescue is off for this slot", t90_decided_at=end - timedelta(minutes=90),
                created_by=cook.id, created_at=now)
    db.add(meal)
    db.flush()
    rice = dishes["Rice"]
    reserve_g = (p90 - p50) * rice.cooked_g_per_diner  # 30 x 200 g = 6.0 kg
    rice_line = _add_menu_dish(db, meal, rice, is_reserve=True, usual_g=110000,
                               line_g=p50 * rice.cooked_g_per_diner, reserve_g=reserve_g)
    sambhar = dishes["Sambhar"]
    _add_menu_dish(db, meal, sambhar, is_reserve=False, usual_g=80000,
                   line_g=p50 * sambhar.cooked_g_per_diner, reserve_g=0)

    batch = ReserveBatch(meal_id=meal.id, meal_dish_id=rice_line.id,
                         batch_no=f"{kitchen.code}-{day:%Y%m%d}-D", food_name=rice.name, is_veg=rice.is_veg,
                         planned_g=reserve_g, lidded_weight_g=reserve_g, prepared_at=_at(day, time(19, 0)),
                         lidded_at=_at(day, time(19, 15)), status=BatchStatus.TO_DISPOSE,
                         worst_colour=Colour.RED, dispose_reason="SAFECLOCK_RED", created_at=now)
    db.add(batch)
    db.flush()
    readings = [(time(19, 15), "74.0", ProbeKind.LID), (time(19, 45), "70.5", ProbeKind.ROUTINE),
                (time(20, 15), "66.0", ProbeKind.ROUTINE)]
    for at, temp, kind in readings:
        db.add(ProbeReading(batch_id=batch.id, temp_c=Decimal(temp), read_at=_at(day, at), kind=kind,
                            recorded_by=cook.id, note="sample data"))
    db.flush()
