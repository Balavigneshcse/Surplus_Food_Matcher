"""Public endpoints: open meals and opt-outs (CSRF check only, rate-limited).

Endpoints arrive in a later build phase; the prefix and the role/CSRF rules are fixed here.
"""
from fastapi import APIRouter, Depends

from app.core.security import csrf_protect

router = APIRouter(prefix="/api/public", tags=["public"],
                   dependencies=[Depends(csrf_protect)])
