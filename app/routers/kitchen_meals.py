"""Kitchen meals: list, create, view, edit, override, issue cook card, live count (KITCHEN only).

(Close meal and meals.csv arrive with their phases.) Every command answers the full meal view.
"""
import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.clock import ClockDep
from app.core.db import DbSession
from app.core.security import KitchenUser, csrf_protect, kitchen_user
from app.schemas.planning import LiveCountIn, MealCreateIn, MealListOut, MealUpdateIn, MealView, OverrideIn
from app.services import meals

router = APIRouter(prefix="/api/kitchen", tags=["kitchen"],
                   dependencies=[Depends(kitchen_user), Depends(csrf_protect)])


@router.get("/meals")
def list_meals(user: KitchenUser, db: DbSession, clock: ClockDep,
               date: Annotated[dt.date | None, Query(description="IST date; default today")] = None) -> MealListOut:
    return meals.list_meals(db, user, date or clock.today(), clock.now())


@router.post("/meals", status_code=201)
def create_meal(body: MealCreateIn, user: KitchenUser, db: DbSession, clock: ClockDep) -> MealView:
    now = clock.now()
    meal_id = meals.create_meal(db, user, body, now)
    return meals.meal_view(db, user, meal_id, now)


@router.get("/meals/{meal_id}")
def get_meal(meal_id: int, user: KitchenUser, db: DbSession, clock: ClockDep) -> MealView:
    return meals.meal_view(db, user, meal_id, clock.now())


@router.put("/meals/{meal_id}")
def update_meal(meal_id: int, body: MealUpdateIn, user: KitchenUser, db: DbSession, clock: ClockDep) -> MealView:
    meals.update_meal(db, user, meal_id, body)
    return meals.meal_view(db, user, meal_id, clock.now())


@router.post("/meals/{meal_id}/override")
def override(meal_id: int, body: OverrideIn, user: KitchenUser, db: DbSession, clock: ClockDep) -> MealView:
    meals.override(db, user, meal_id, body)
    return meals.meal_view(db, user, meal_id, clock.now())


@router.post("/meals/{meal_id}/issue-cook-card")
def issue_cook_card(meal_id: int, user: KitchenUser, db: DbSession, clock: ClockDep) -> MealView:
    now = clock.now()
    meals.issue_cook_card(db, user, meal_id, now)
    return meals.meal_view(db, user, meal_id, now)


@router.post("/meals/{meal_id}/live-count")
def live_count(meal_id: int, body: LiveCountIn, user: KitchenUser, db: DbSession, clock: ClockDep) -> MealView:
    now = clock.now()
    meals.set_live_count(db, user, meal_id, body, now)
    return meals.meal_view(db, user, meal_id, now)
