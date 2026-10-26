"""Kitchen setup: meal slots (times, cutoff, ratio, buffer, partner, ...) and dishes (g/diner, Tamil name).

Every function takes the CurrentUser and only sees that user's kitchen: another kitchen's slot or dish
answers 404, exactly like a missing one.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import CurrentUser
from app.models import Dish, Kitchen, Meal, MealDish, MealSlot, Ngo, Partnership
from app.schemas.common import MealStatus, Slot
from app.schemas.planning import (DishIn, DishOut, KitchenInfo, PartnerOption, SlotIn, SlotListOut,
                                  SlotOut)

SLOT_ORDER = {Slot.BREAKFAST: 0, Slot.LUNCH: 1, Slot.DINNER: 2}


def get_kitchen(db: Session, user: CurrentUser) -> Kitchen:
    kitchen = db.get(Kitchen, user.kitchen_id) if user.kitchen_id is not None else None
    if kitchen is None:
        raise ApiError(404, "NOT_FOUND", "Kitchen not found")
    return kitchen


def get_slot(db: Session, user: CurrentUser, slot_id: int) -> MealSlot:
    slot = db.scalar(select(MealSlot).where(MealSlot.id == slot_id, MealSlot.kitchen_id == user.kitchen_id))
    if slot is None:
        raise ApiError(404, "NOT_FOUND", "Meal slot not found")
    return slot


def get_dish(db: Session, user: CurrentUser, dish_id: int) -> Dish:
    dish = db.scalar(select(Dish).where(Dish.id == dish_id, Dish.kitchen_id == user.kitchen_id))
    if dish is None:
        raise ApiError(404, "NOT_FOUND", "Dish not found")
    return dish


# ---------------------------------------------------------------- slots

def partner_ngos(db: Session, kitchen_id: int) -> list[Ngo]:
    """Active NGOs with an active MoU with this kitchen: the only ones that can be a standing partner.
    (The T-90 step checks the MoU dates again when it decides.)"""
    return list(db.scalars(
        select(Ngo).join(Partnership, Partnership.ngo_id == Ngo.id)
        .where(Partnership.kitchen_id == kitchen_id, Partnership.active, Ngo.active)
        .order_by(Ngo.name)))


def slot_out(db: Session, slot: MealSlot) -> SlotOut:
    out = SlotOut.model_validate(slot)
    if slot.standing_ngo_id is not None:
        ngo = db.get(Ngo, slot.standing_ngo_id)
        out.standing_ngo_name = ngo.name if ngo else None
    return out


def list_slots(db: Session, user: CurrentUser) -> SlotListOut:
    kitchen = get_kitchen(db, user)
    slots = db.scalars(select(MealSlot).where(MealSlot.kitchen_id == kitchen.id))
    ordered = sorted(slots, key=lambda s: SLOT_ORDER.get(s.slot, 9))
    return SlotListOut(kitchen=KitchenInfo.model_validate(kitchen),
                       slots=[slot_out(db, s) for s in ordered],
                       partners=[PartnerOption(id=n.id, name=n.name) for n in partner_ngos(db, kitchen.id)])


def update_slot(db: Session, user: CurrentUser, slot_id: int, body: SlotIn) -> SlotOut:
    slot = get_slot(db, user, slot_id)
    if body.standing_ngo_id is not None:
        partner_ids = {n.id for n in partner_ngos(db, slot.kitchen_id)}
        if body.standing_ngo_id not in partner_ids:
            raise ApiError(409, "NOT_A_PARTNER", "The standing partner must be an NGO with an active MoU")
    slot.service_start = body.service_start
    slot.service_end = body.service_end
    slot.optout_cutoff_min = body.optout_cutoff_min
    slot.attendance_ratio = body.attendance_ratio
    slot.buffer_pct = body.buffer_pct
    slot.share_arrived_by_t90 = body.share_arrived_by_t90
    slot.standing_ngo_id = body.standing_ngo_id
    slot.pickup_offset_min = body.pickup_offset_min
    slot.rescue_enabled = body.rescue_enabled
    db.commit()
    return slot_out(db, slot)


# ---------------------------------------------------------------- dishes

def list_dishes(db: Session, user: CurrentUser) -> list[DishOut]:
    dishes = db.scalars(select(Dish).where(Dish.kitchen_id == user.kitchen_id).order_by(Dish.name))
    return [DishOut.model_validate(d) for d in dishes]


def _copy_dish_fields(dish: Dish, body: DishIn) -> None:
    dish.name = body.name
    dish.name_ta = body.name_ta
    dish.is_veg = body.is_veg
    dish.cooked_g_per_diner = body.cooked_g_per_diner
    dish.raw_g_per_diner = body.raw_g_per_diner
    dish.cost_per_kg_inr = body.cost_per_kg_inr
    dish.active = body.active


def create_dish(db: Session, user: CurrentUser, body: DishIn) -> DishOut:
    kitchen = get_kitchen(db, user)
    dish = Dish(kitchen_id=kitchen.id)
    _copy_dish_fields(dish, body)
    db.add(dish)
    db.commit()  # a duplicate name answers 409 DISH_NAME_TAKEN (uq_dish_kitchen_name)
    return DishOut.model_validate(dish)


def is_open_reserve_dish(db: Session, dish_id: int) -> bool:
    """True if this dish is the reserve dish of a meal that is not closed yet."""
    found = db.scalar(select(MealDish.id).join(Meal, Meal.id == MealDish.meal_id)
                      .where(MealDish.dish_id == dish_id, MealDish.is_reserve, Meal.status != MealStatus.CLOSED)
                      .limit(1))
    return found is not None


def update_dish(db: Session, user: CurrentUser, dish_id: int, body: DishIn) -> DishOut:
    """Meals copy g/diner when they are planned, so an edit here never changes an issued cook card."""
    dish = get_dish(db, user, dish_id)
    if dish.is_veg and not body.is_veg and is_open_reserve_dish(db, dish.id):
        # plan 8.2: the reserve vessel is veg in the MVP (veg and non-veg are never mixed)
        raise ApiError(409, "RESERVE_MUST_BE_VEG",
                       f"{dish.name} is the reserve dish of a meal that is not closed yet; the reserve must be veg")
    _copy_dish_fields(dish, body)
    db.commit()
    return DishOut.model_validate(dish)
