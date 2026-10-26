"""Admin: kitchens, NGOs (FSSAI verify), MoUs, users and the admin dashboard (ADMIN only).

Endpoints arrive in a later build phase; the prefix and the role/CSRF rules are fixed here.
"""
from fastapi import APIRouter, Depends

from app.core.security import admin_user, csrf_protect

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(admin_user), Depends(csrf_protect)])
