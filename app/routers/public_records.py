"""Public batch records: record + label + probe log, and the QR PNG (CSRF check only).

Endpoints arrive in a later build phase; the prefix and the role/CSRF rules are fixed here.
"""
from fastapi import APIRouter, Depends

from app.core.security import csrf_protect

router = APIRouter(prefix="/api/public/records", tags=["public"],
                   dependencies=[Depends(csrf_protect)])
