"""NGO offers inbox (accept/decline) and standing-slot status (NGO only).

Endpoints arrive in a later build phase; the prefix and the role/CSRF rules are fixed here.
"""
from fastapi import APIRouter, Depends

from app.core.security import csrf_protect, ngo_user

router = APIRouter(prefix="/api/ngo", tags=["ngo"],
                   dependencies=[Depends(ngo_user), Depends(csrf_protect)])
