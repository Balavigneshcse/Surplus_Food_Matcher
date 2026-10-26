"""Meals: create and edit (PLANNED only), the live forecast, override, issue the cook card (by the manager
or by the scheduler at the cutoff), start service, the live door count, and the full meal view.

Life of a meal:  PLANNED --issue (button, or the cutoff)--> ISSUED --service start--> IN_SERVICE --> CLOSED

- While PLANNED the forecast is computed live on every read, from the opt-outs so far and the slot's
  current attendance ratio and buffer. A MANUAL forecast (override) keeps the manager's numbers.
- Issuing freezes everything: P50/P90, the rule numbers, opted_out_count, attendance_ratio, buffer_pct,
  and each dish's line_g / reserve_g. An issued card never changes again.
- Every function takes the CurrentUser and only sees that user's kitchen: another kitchen's meal is 404.
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.core.clock import IST
from app.core.errors import ApiError
from app.core.security import CurrentUser
from app.models import Dish, Kitchen, Meal, MealDish, MealSlot
from app.rules.cook_card import DishInput, basis_used, cook_line, menu_problem
from app.rules.forecast import (MANUAL, RULE_V1, Forecaster, ForecastInput, RuleBasedForecaster,
                                eligible_diners, manual_forecast)
from app.schemas.common import MealStatus, T90Status
from app.schemas.planning import (CookCardLine, ForecastOut, LiveCountIn, MealCreateIn, MealListOut,
                                  MealSummary, MealUpdateIn, MealView, MenuDishIn, OverrideIn, T90Out)
from app.services import kitchen_setup, opt_outs

log = logging.getLogger(__name__)

# The port: the rule today; the team's own ML forecaster can be plugged in here later.
FORECASTER: Forecaster = RuleBasedForecaster()

TALLY_STATUSES = (MealStatus.ISSUED, MealStatus.IN_SERVICE)  # the door tally runs during service


# ---------------------------------------------------------------- loading (kitchen scoping)

def lock_meal_row(db: Session, meal_id: int, kitchen_id: int | None = None) -> None:
    """Lock the meal row until this transaction ends (SELECT ... FOR UPDATE).

    Issue, edit and override take this lock; an opt-out takes a shared lock on the same row
    (services/opt_outs.py). So an opt-out that is being saved while the card is issued is either counted
    in the frozen numbers (the issue waits for it) or refused with 409 OPTOUT_CLOSED (it waits for the issue)."""
    stmt = select(Meal.id).where(Meal.id == meal_id)
    if kitchen_id is not None:
        stmt = stmt.where(Meal.kitchen_id == kitchen_id)
    db.execute(stmt.with_for_update())


def get_meal(db: Session, user: CurrentUser, meal_id: int, lock: bool = False) -> Meal:
    """The meal with its slot and menu, freshly read. Another kitchen's meal is 404, like a missing one.
    lock=True first locks the row (for commands that change the meal)."""
    if lock:
        lock_meal_row(db, meal_id, user.kitchen_id)
    meal = db.scalar(
        select(Meal).where(Meal.id == meal_id, Meal.kitchen_id == user.kitchen_id)
        .options(joinedload(Meal.slot), selectinload(Meal.dishes).joinedload(MealDish.dish))
        .execution_options(populate_existing=True))
    if meal is None:
        raise ApiError(404, "NOT_FOUND", "Meal not found")
    return meal


def cutoff_at(meal: Meal) -> datetime:
    """Opt-outs close, and the card issues itself, optout_cutoff_min before service starts."""
    return meal.service_start_at - timedelta(minutes=meal.slot.optout_cutoff_min)


def _today(now: datetime) -> date:
    return now.astimezone(IST).date()


def _require_planned(meal: Meal) -> None:
    if meal.status != MealStatus.PLANNED:
        raise ApiError(409, "MEAL_NOT_PLANNED", "The cook card is already issued: this meal can no longer change")


def _check_version(meal: Meal, version: int | None) -> None:
    if version is not None and version != meal.version:
        raise ApiError(409, "CONCURRENT_EDIT", "Someone else changed this just now. Reload and try again.")


# ---------------------------------------------------------------- the numbers: live or frozen

@dataclass(frozen=True)
class MealNumbers:
    opt_out_rows: int  # students who opted out on optout.html
    opted_out: int  # + extra_opt_outs
    eligible: int
    attendance_ratio: Decimal
    buffer_pct: Decimal
    p50: int
    p90: int
    method: str
    rule_p50: int
    rule_p90: int
    frozen: bool


def meal_numbers(db: Session, meal: Meal) -> MealNumbers:
    """PLANNED: computed live now. ISSUED and later: the numbers frozen at issue."""
    if meal.status == MealStatus.PLANNED:
        slot = meal.slot
        rows = opt_outs.count_for(db, meal.kitchen_id, slot.slot, meal.meal_date)
        opted_out = rows + meal.extra_opt_outs
        rule = FORECASTER.forecast(ForecastInput(registered=meal.registered_count, opted_out=opted_out,
                                                 attendance_ratio=slot.attendance_ratio,
                                                 buffer_pct=slot.buffer_pct))
        manual = meal.forecast_method == MANUAL
        return MealNumbers(opt_out_rows=rows, opted_out=opted_out,
                           eligible=eligible_diners(meal.registered_count, opted_out),
                           attendance_ratio=slot.attendance_ratio, buffer_pct=slot.buffer_pct,
                           p50=meal.p50 if manual else rule.p50, p90=meal.p90 if manual else rule.p90,
                           method=meal.forecast_method, rule_p50=rule.p50, rule_p90=rule.p90, frozen=False)
    opted_out = meal.opted_out_count or 0
    return MealNumbers(opt_out_rows=max(0, opted_out - meal.extra_opt_outs), opted_out=opted_out,
                       eligible=eligible_diners(meal.registered_count, opted_out),
                       attendance_ratio=meal.attendance_ratio, buffer_pct=meal.buffer_pct,
                       p50=meal.p50, p90=meal.p90, method=meal.forecast_method,
                       rule_p50=meal.rule_p50 if meal.rule_p50 is not None else meal.p50,
                       rule_p90=meal.rule_p90 if meal.rule_p90 is not None else meal.p90, frozen=True)


def _dish_input(md: MealDish) -> DishInput:
    return DishInput(cooked_g_per_diner=md.cooked_g_per_diner, raw_g_per_diner=md.raw_g_per_diner,
                     is_reserve=md.is_reserve, is_veg=md.dish.is_veg)


def side_dish_basis(meal: Meal, numbers: MealNumbers, kitchen: Kitchen) -> str:
    """PLANNED: the kitchen's setting. Issued: the basis the frozen card was made with."""
    if not numbers.frozen:
        return kitchen.side_dish_basis
    sides = [(md.line_g, md.cooked_g_per_diner) for md in meal.dishes if not md.is_reserve and md.line_g is not None]
    return basis_used(numbers.p50, numbers.p90, sides)


def cook_card_lines(meal: Meal, numbers: MealNumbers, basis: str) -> list[CookCardLine]:
    lines = []
    for md in meal.dishes:
        card = cook_line(numbers.p50, numbers.p90, _dish_input(md), basis)
        line_g = md.line_g if numbers.frozen and md.line_g is not None else card.line_g
        reserve_g = md.reserve_g if numbers.frozen and md.reserve_g is not None else card.reserve_g
        lines.append(CookCardLine(
            meal_dish_id=md.id, dish_id=md.dish_id, name=md.dish.name, name_ta=md.dish.name_ta,
            is_veg=md.dish.is_veg, is_reserve=md.is_reserve, cooked_g_per_diner=md.cooked_g_per_diner,
            raw_g_per_diner=md.raw_g_per_diner, line_g=line_g, reserve_g=reserve_g, top_up_g=card.top_up_g,
            raw_g=card.raw_g, raw_diners=card.raw_diners, planned_g=line_g + reserve_g, usual_g=md.usual_g))
    lines.sort(key=lambda line: not line.is_reserve)  # the reserve dish first, then the menu order
    return lines


# ---------------------------------------------------------------- views

def meal_view(db: Session, user: CurrentUser, meal_id: int, now: datetime) -> MealView:
    meal = get_meal(db, user, meal_id)
    kitchen = db.get(Kitchen, meal.kitchen_id)
    numbers = meal_numbers(db, meal)
    basis = side_dish_basis(meal, numbers, kitchen)
    lines = cook_card_lines(meal, numbers, basis)
    cutoff = cutoff_at(meal)
    return MealView(
        id=meal.id, kitchen_code=kitchen.code, kitchen_name=kitchen.name, slot_id=meal.meal_slot_id,
        slot=meal.slot.slot, date=meal.meal_date, status=meal.status,
        service_start_at=meal.service_start_at, service_end_at=meal.service_end_at, cutoff_at=cutoff,
        optout_open=meal.status == MealStatus.PLANNED and now < cutoff,
        registered_count=meal.registered_count, opt_out_rows=numbers.opt_out_rows,
        extra_opt_outs=meal.extra_opt_outs, opted_out=numbers.opted_out, eligible=numbers.eligible,
        attendance_ratio=numbers.attendance_ratio, buffer_pct=numbers.buffer_pct, side_dish_basis=basis,
        forecast=ForecastOut(p50=numbers.p50, p90=numbers.p90, method=numbers.method, rule_p50=numbers.rule_p50,
                             rule_p90=numbers.rule_p90, override_reason=meal.override_reason,
                             frozen=numbers.frozen),
        cook_card=lines, reserve_g=sum(line.reserve_g for line in lines), issued_at=meal.issued_at,
        live_count=meal.live_count, live_count_at=meal.live_count_at,
        t90=T90Out(status=meal.t90_status, live_count=meal.t90_live_count, projected=meal.t90_projected,
                   expected_surplus_g=meal.t90_expected_surplus_g, reason=meal.t90_reason,
                   decided_at=meal.t90_decided_at),
        actual_diners=meal.actual_diners, ran_short=meal.ran_short, closed_at=meal.closed_at,
        version=meal.version, server_now=now)


def list_meals(db: Session, user: CurrentUser, day: date, now: datetime) -> MealListOut:
    meals = db.scalars(
        select(Meal).where(Meal.kitchen_id == user.kitchen_id, Meal.meal_date == day)
        .options(joinedload(Meal.slot), selectinload(Meal.dishes).joinedload(MealDish.dish))
        .order_by(Meal.service_start_at)
        .execution_options(populate_existing=True)).all()
    summaries = []
    for meal in meals:
        numbers = meal_numbers(db, meal)
        reserve_dishes = [md for md in meal.dishes if md.is_reserve]
        if numbers.frozen and reserve_dishes and reserve_dishes[0].reserve_g is not None:
            reserve_g = reserve_dishes[0].reserve_g
        else:
            reserve_g = sum((numbers.p90 - numbers.p50) * md.cooked_g_per_diner for md in reserve_dishes)
        summaries.append(MealSummary(
            id=meal.id, slot_id=meal.meal_slot_id, slot=meal.slot.slot, date=meal.meal_date, status=meal.status,
            service_start_at=meal.service_start_at, service_end_at=meal.service_end_at, cutoff_at=cutoff_at(meal),
            registered_count=meal.registered_count, opted_out=numbers.opted_out, p50=numbers.p50,
            p90=numbers.p90, method=numbers.method, frozen=numbers.frozen, reserve_g=reserve_g,
            live_count=meal.live_count, t90_status=meal.t90_status))
    return MealListOut(date=day, meals=summaries, server_now=now)


# ---------------------------------------------------------------- create and edit (PLANNED only)

def _menu(db: Session, user: CurrentUser, dishes_in: list[MenuDishIn]) -> list[tuple[Dish, MenuDishIn]]:
    """Check the menu: this kitchen's active dishes, each once, exactly one reserve dish, and it is veg."""
    ids = [d.dish_id for d in dishes_in]
    if len(set(ids)) != len(ids):
        raise ApiError(400, "DISH_ALREADY_ON_MENU", "A dish is on the menu twice")
    found = {d.id: d for d in db.scalars(select(Dish).where(Dish.kitchen_id == user.kitchen_id, Dish.id.in_(ids)))}
    menu = []
    for item in dishes_in:
        dish = found.get(item.dish_id)
        if dish is None:
            raise ApiError(404, "NOT_FOUND", "Dish not found")
        if not dish.active:
            raise ApiError(409, "DISH_INACTIVE", f"{dish.name} is switched off in setup")
        menu.append((dish, item))
    problem = menu_problem([DishInput(dish.cooked_g_per_diner, dish.raw_g_per_diner, item.is_reserve, dish.is_veg)
                            for dish, item in menu])
    if problem == "ONE_RESERVE_DISH":
        raise ApiError(409, problem, "Mark exactly one dish as the reserve dish (one lidded vessel)")
    if problem == "RESERVE_MUST_BE_VEG":
        raise ApiError(409, problem, "The reserve dish must be veg")
    return menu


def _add_menu(db: Session, meal: Meal, menu: list[tuple[Dish, MenuDishIn]]) -> None:
    for dish, item in menu:
        # g/diner are copied from the dish, so later dish edits never change this meal's card
        db.add(MealDish(meal_id=meal.id, dish_id=dish.id, is_reserve=item.is_reserve,
                        cooked_g_per_diner=dish.cooked_g_per_diner, raw_g_per_diner=dish.raw_g_per_diner,
                        usual_g=item.usual_g))


def create_meal(db: Session, user: CurrentUser, body: MealCreateIn, now: datetime) -> int:
    """Create a meal from the slot defaults. Returns the new meal's id."""
    slot = kitchen_setup.get_slot(db, user, body.slot_id)
    kitchen = kitchen_setup.get_kitchen(db, user)
    if body.date < _today(now):
        raise ApiError(409, "MEAL_DATE_PAST", "Meals can be planned for today or later")
    exists = db.scalar(select(Meal.id).where(Meal.kitchen_id == kitchen.id, Meal.meal_slot_id == slot.id,
                                             Meal.meal_date == body.date))
    if exists is not None:
        raise ApiError(409, "MEAL_EXISTS", "This meal already exists")
    menu = _menu(db, user, body.dishes)
    meal = Meal(kitchen_id=kitchen.id, meal_slot_id=slot.id, meal_date=body.date,
                service_start_at=datetime.combine(body.date, slot.service_start, IST),
                service_end_at=datetime.combine(body.date, slot.service_end, IST),
                status=MealStatus.PLANNED,
                registered_count=(body.registered_count if body.registered_count is not None
                                  else kitchen.registered_diners),
                extra_opt_outs=body.extra_opt_outs,
                attendance_ratio=slot.attendance_ratio, buffer_pct=slot.buffer_pct,  # refreshed again at issue
                forecast_method=RULE_V1, live_count=0, t90_status=T90Status.PENDING,
                created_by=user.id, created_at=now)
    db.add(meal)
    db.flush()  # gives meal.id (the unique constraint is the backstop for a double create)
    _add_menu(db, meal, menu)
    db.commit()
    return meal.id


def update_meal(db: Session, user: CurrentUser, meal_id: int, body: MealUpdateIn) -> None:
    """Edit the counts and the menu while the meal is PLANNED."""
    meal = get_meal(db, user, meal_id, lock=True)
    _require_planned(meal)
    _check_version(meal, body.version)
    menu = _menu(db, user, body.dishes)
    meal.registered_count = body.registered_count
    meal.extra_opt_outs = body.extra_opt_outs
    meal.attendance_ratio = meal.slot.attendance_ratio
    meal.buffer_pct = meal.slot.buffer_pct
    flag_modified(meal, "registered_count")  # always UPDATE the meal row, so its version goes up
    for md in list(meal.dishes):
        db.delete(md)
    db.flush()  # old menu rows go first: the one-reserve-dish index must never see two
    _add_menu(db, meal, menu)
    db.commit()


def override(db: Session, user: CurrentUser, meal_id: int, body: OverrideIn) -> None:
    """MANUAL forecast (events, caterers, a known change): P90 >= P50 and a reason. The rule numbers are kept."""
    meal = get_meal(db, user, meal_id, lock=True)
    _require_planned(meal)
    _check_version(meal, body.version)
    if not body.reason:
        raise ApiError(400, "OVERRIDE_NEEDS_REASON", "Say why you are changing the forecast")
    if body.p90 < body.p50:
        raise ApiError(400, "P90_BELOW_P50", "The high forecast (P90) must not be below the expected one (P50)")
    rule = meal_numbers(db, meal)
    manual = manual_forecast(body.p50, body.p90)
    meal.forecast_method = manual.method
    meal.p50, meal.p90 = manual.p50, manual.p90
    meal.rule_p50, meal.rule_p90 = rule.rule_p50, rule.rule_p90
    meal.override_reason = body.reason
    db.commit()


# ---------------------------------------------------------------- issue the cook card (freeze)

def _issue(db: Session, meal: Meal, now: datetime) -> None:
    numbers = meal_numbers(db, meal)  # live numbers, the last time
    kitchen = db.get(Kitchen, meal.kitchen_id)
    for md in meal.dishes:
        card = cook_line(numbers.p50, numbers.p90, _dish_input(md), kitchen.side_dish_basis)
        md.line_g, md.reserve_g = card.line_g, card.reserve_g
    meal.opted_out_count = numbers.opted_out
    meal.attendance_ratio, meal.buffer_pct = numbers.attendance_ratio, numbers.buffer_pct
    meal.p50, meal.p90 = numbers.p50, numbers.p90
    meal.rule_p50, meal.rule_p90 = numbers.rule_p50, numbers.rule_p90
    meal.issued_at = now
    meal.status = MealStatus.ISSUED


def issue_cook_card(db: Session, user: CurrentUser, meal_id: int, now: datetime) -> None:
    """The manager's button: freeze the numbers now (the scheduler does the same at the cutoff)."""
    meal = get_meal(db, user, meal_id, lock=True)  # waits for an opt-out being saved, so it is counted
    _require_planned(meal)  # re-checked under the lock: the scheduler may have issued it a moment ago
    _issue(db, meal, now)
    db.commit()


# ---------------------------------------------------------------- live door count

def set_live_count(db: Session, user: CurrentUser, meal_id: int, body: LiveCountIn, now: datetime) -> None:
    """Set the door tally ({count}) or add to it ({delta}). One UPDATE, so two phones tapping +1 at the same
    moment both count."""
    meal = get_meal(db, user, meal_id)
    if meal.status not in TALLY_STATUSES:
        raise ApiError(409, "MEAL_NOT_IN_SERVICE", "Issue the cook card first; the door tally runs during service")
    stmt = update(Meal).where(Meal.id == meal.id, Meal.status.in_(TALLY_STATUSES))
    if body.count is not None:
        new_count = body.count
    else:
        if meal.live_count + body.delta < 0:
            raise ApiError(409, "COUNT_BELOW_ZERO", "The door tally cannot go below zero")
        new_count = Meal.live_count + body.delta
        stmt = stmt.where(Meal.live_count + body.delta >= 0)
    result = db.execute(stmt.values(live_count=new_count, live_count_at=now, version=Meal.version + 1)
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise ApiError(409, "CONCURRENT_EDIT", "Someone else changed this just now. Reload and try again.")
    db.commit()


# ---------------------------------------------------------------- scheduler steps 1 and 2 (plan 8.6)

def find_past_cutoff(db: Session, now: datetime) -> list[int]:
    """Step 1: PLANNED meals whose opt-out cutoff has passed."""
    rows = db.execute(select(Meal.id, Meal.service_start_at, MealSlot.optout_cutoff_min)
                      .join(MealSlot, MealSlot.id == Meal.meal_slot_id)
                      .where(Meal.status == MealStatus.PLANNED)
                      .order_by(Meal.id)).all()
    return [meal_id for meal_id, start, cutoff_min in rows if now >= start - timedelta(minutes=cutoff_min)]


def auto_issue(db: Session, meal_id: int, now: datetime) -> None:
    """Step 1: issue the cook card at the cutoff. Re-checks the state first (the manager may have issued it)."""
    lock_meal_row(db, meal_id)  # same lock as the manager's button and the opt-outs
    meal = db.scalar(select(Meal).where(Meal.id == meal_id)
                     .options(joinedload(Meal.slot), selectinload(Meal.dishes).joinedload(MealDish.dish)))
    if meal is None or meal.status != MealStatus.PLANNED or now < cutoff_at(meal):
        return
    _issue(db, meal, now)
    db.commit()
    log.info("meal %s: cook card issued at the cutoff (P50 %s / P90 %s)", meal.id, meal.p50, meal.p90)


def find_past_start(db: Session, now: datetime) -> list[int]:
    """Step 2: ISSUED meals whose service has started."""
    return list(db.scalars(select(Meal.id).where(Meal.status == MealStatus.ISSUED, Meal.service_start_at <= now)
                           .order_by(Meal.id)))


def start_service(db: Session, meal_id: int, now: datetime) -> None:
    """Step 2: ISSUED -> IN_SERVICE, as one conditional UPDATE (does nothing if the state moved on)."""
    db.execute(update(Meal)
               .where(Meal.id == meal_id, Meal.status == MealStatus.ISSUED, Meal.service_start_at <= now)
               .values(status=MealStatus.IN_SERVICE, version=Meal.version + 1)
               .execution_options(synchronize_session=False))
    db.commit()
