"""Kitchen setup: meal slots and dishes (KITCHEN only). Routers parse input and call the service."""
from fastapi import APIRouter, Depends

from app.core.db import DbSession
from app.core.security import KitchenUser, csrf_protect, kitchen_user
from app.schemas.planning import DishIn, DishOut, SlotIn, SlotListOut, SlotOut
from app.services import kitchen_setup

router = APIRouter(prefix="/api/kitchen", tags=["kitchen"],
                   dependencies=[Depends(kitchen_user), Depends(csrf_protect)])


@router.get("/slots")
def list_slots(user: KitchenUser, db: DbSession) -> SlotListOut:
    """The kitchen's meal slots, plus the NGOs with an MoU that can be a slot's standing partner."""
    return kitchen_setup.list_slots(db, user)


@router.put("/slots/{slot_id}")
def update_slot(slot_id: int, body: SlotIn, user: KitchenUser, db: DbSession) -> SlotOut:
    return kitchen_setup.update_slot(db, user, slot_id, body)


@router.get("/dishes")
def list_dishes(user: KitchenUser, db: DbSession) -> list[DishOut]:
    return kitchen_setup.list_dishes(db, user)


@router.post("/dishes", status_code=201)
def create_dish(body: DishIn, user: KitchenUser, db: DbSession) -> DishOut:
    return kitchen_setup.create_dish(db, user, body)


@router.put("/dishes/{dish_id}")
def update_dish(dish_id: int, body: DishIn, user: KitchenUser, db: DbSession) -> DishOut:
    return kitchen_setup.update_dish(db, user, dish_id, body)
