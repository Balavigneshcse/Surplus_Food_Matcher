"""User accounts: login check and the /api/me view. (Admin user management arrives with the admin phase.)"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import CurrentUser, dummy_hash, password_fits_bcrypt, password_hash
from app.models.org import AppUser, Kitchen, Ngo
from app.schemas.org import MeOut


def find_by_username(db: Session, username: str) -> AppUser | None:
    return db.scalar(select(AppUser).where(AppUser.username == username))


def authenticate(db: Session, username: str, password: str) -> AppUser | None:
    """Return the user if the password is right, else None."""
    if not password_fits_bcrypt(password):  # bcrypt 5 rejects > 72 bytes; treat it as wrong
        return None
    user = find_by_username(db, username)
    if user is None or not user.enabled:
        password_hash.verify(password, dummy_hash())  # same work either way, so timing reveals nothing
        return None
    if not password_hash.verify(password, user.password_hash):
        return None
    return user


def me_view(db: Session, user: CurrentUser, sample_data: bool, now: datetime) -> MeOut:
    row = db.get(AppUser, user.id)
    if row is None:
        raise ApiError(401, "NOT_LOGGED_IN", "Please log in")
    kitchen = db.get(Kitchen, user.kitchen_id) if user.kitchen_id is not None else None
    ngo = db.get(Ngo, user.ngo_id) if user.ngo_id is not None else None
    return MeOut(
        id=row.id, username=row.username, display_name=row.display_name, role=row.role,
        kitchen_id=user.kitchen_id, kitchen_code=kitchen.code if kitchen else None,
        kitchen_name=kitchen.name if kitchen else None,
        ngo_id=user.ngo_id, ngo_name=ngo.name if ngo else None,
        sample_data=sample_data, server_now=now,
    )
