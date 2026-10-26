"""Kitchen meals: create/edit, override, issue cook card, live count, close, meals.csv (KITCHEN only).

Endpoints arrive in a later build phase; the prefix and the role/CSRF rules are fixed here.
"""
from fastapi import APIRouter, Depends

from app.core.security import csrf_protect, kitchen_user

router = APIRouter(prefix="/api/kitchen", tags=["kitchen"],
                   dependencies=[Depends(kitchen_user), Depends(csrf_protect)])
