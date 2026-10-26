"""Session login. /api/auth/** has the CSRF check only (no login needed).

Login and logout each issue a new CSRF token, so api.js fetches a fresh one afterwards.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import ApiError
from app.core.security import csrf_protect, new_csrf_token
from app.schemas.common import CsrfOut
from app.schemas.org import LoginOut
from app.services import users

router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(csrf_protect)])

CSRF_COOKIE = "XSRF-TOKEN"
SESSION_HOURS = 12


def _set_csrf_cookie(response: Response, token: str) -> None:
    # Readable by JavaScript on purpose (not HttpOnly): api.js copies it into the X-CSRF-Token header.
    response.set_cookie(CSRF_COOKIE, token, max_age=SESSION_HOURS * 3600, path="/", samesite="lax",
                        secure=get_settings().secure_cookies, httponly=False)


@router.get("/csrf")
def csrf(request: Request, response: Response) -> CsrfOut:
    token = request.session.get("csrf")
    if not token:
        token = new_csrf_token()
        request.session["csrf"] = token
    _set_csrf_cookie(response, token)
    return CsrfOut(csrf_token=token)


@router.post("/login")
def login(request: Request, response: Response, db: DbSession,
          username: Annotated[str, Form(min_length=1, max_length=50)],
          password: Annotated[str, Form(min_length=1)]) -> LoginOut:
    user = users.authenticate(db, username, password)
    if user is None:
        raise ApiError(401, "BAD_CREDENTIALS", "Wrong username or password")
    request.session.clear()
    request.session["uid"] = user.id
    token = new_csrf_token()
    request.session["csrf"] = token
    _set_csrf_cookie(response, token)
    return LoginOut(role=user.role, display_name=user.display_name, csrf_token=token)


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    request.session.clear()  # SessionMiddleware then expires the session cookie by itself
    response = Response(status_code=204)
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response
