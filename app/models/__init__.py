"""Import every model module so SQLAlchemy (and Alembic) see all 14 tables."""
from app.models.offer import Offer
from app.models.org import AppUser, Kitchen, Ngo, Partnership
from app.models.planning import Dish, Meal, MealDish, MealSlot, OptOut
from app.models.record import BatchRecord
from app.models.route import RouteLog
from app.models.safety import ProbeReading, ReserveBatch

__all__ = [
    "AppUser", "BatchRecord", "Dish", "Kitchen", "Meal", "MealDish", "MealSlot", "Ngo", "Offer", "OptOut",
    "Partnership", "ProbeReading", "ReserveBatch", "RouteLog",
]
