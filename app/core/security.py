"""Login sessions, roles and CSRF.

The session (a signed cookie from SessionMiddleware) holds only `uid` and `csrf`.
Every request reloads the user, so disabling a user takes effect at once.
"""
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.db import DbSession
from app.core.errors import ApiError
from app.models.org import AppUser
from app.schemas.common import Role

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MAX_PASSWORD_BYTES = 72  # bcrypt 5 raises ValueError above this, in hash() and verify()

password_hash = PasswordHash((BcryptHasher(),))


@dataclass(frozen=True)
class CurrentUser:
    id: int
    role: str
    kitchen_id: int | None
    ngo_id: int | None


def password_fits_bcrypt(password: str) -> bool:
    return len(password.encode()) <= MAX_PASSWORD_BYTES


@lru_cache
def dummy_hash() -> str:
    """Checked when a username does not exist, so the response time does not reveal it."""
    return password_hash.hash(secrets.token_urlsafe(16))


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_protect(request: Request) -> None:
    """Unsafe methods must send X-CSRF-Token equal to the token kept in the signed session."""
    if request.method in SAFE_METHODS:
        return
    sent = request.headers.get("X-CSRF-Token", "")
    expected = request.session.get("csrf", "")
    if not (sent and expected and secrets.compare_digest(sent.encode(), expected.encode())):
        raise ApiError(403, "CSRF_INVALID", "Missing or wrong CSRF token. Reload the page.")


def current_user(request: Request, db: DbSession) -> CurrentUser:
    uid = request.session.get("uid")
    user = db.get(AppUser, uid) if uid is not None else None
    if user is None or not user.enabled:
        raise ApiError(401, "NOT_LOGGED_IN", "Please log in")
    return CurrentUser(id=user.id, role=user.role, kitchen_id=user.kitchen_id, ngo_id=user.ngo_id)


def require_role(role: str):
    def dependency(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
        if user.role != role:
            raise ApiError(403, "FORBIDDEN", "This page is for another role")
        return user
    return dependency


# Create each role dependency once, so FastAPI caches it per request.
admin_user = require_role(Role.ADMIN)
kitchen_user = require_role(Role.KITCHEN)
ngo_user = require_role(Role.NGO)

LoggedInUser = Annotated[CurrentUser, Depends(current_user)]
AdminUser = Annotated[CurrentUser, Depends(admin_user)]
KitchenUser = Annotated[CurrentUser, Depends(kitchen_user)]
NgoUser = Annotated[CurrentUser, Depends(ngo_user)]
