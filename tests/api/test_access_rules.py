"""Security rules per router prefix: 401 / 403, CSRF on unsafe methods, problem+json shape, login flow.

No database is needed: the role tests override `current_user`, and the login-flow tests use a tiny
fake session. Each guarded router is copied (same prefix + same dependencies) with probe endpoints,
because the real routers get their endpoints in later phases.
"""
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app import main
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import install_error_handlers
from app.core.security import (CurrentUser, admin_user, csrf_protect, current_user, dummy_hash, kitchen_user,
                               ngo_user, password_hash)
from app.demo import router as demo_router
from app.models.org import AppUser
from app.routers import (admin, auth, health, kitchen_batches, kitchen_dashboard, kitchen_meals, kitchen_prebook,
                         kitchen_routes, kitchen_setup, me, ngo, ngo_pickups, public, public_records)
from app.services import users

ROLES = ("ADMIN", "KITCHEN", "NGO")
UNSAFE_METHODS = ("POST", "PUT", "DELETE")
PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "code"}

# (name, router, the only role allowed)
ROLE_ROUTERS = [
    ("admin", admin.router, "ADMIN"),
    ("demo", demo_router.router, "ADMIN"),
    ("kitchen_setup", kitchen_setup.router, "KITCHEN"),
    ("kitchen_meals", kitchen_meals.router, "KITCHEN"),
    ("kitchen_prebook", kitchen_prebook.router, "KITCHEN"),
    ("kitchen_batches", kitchen_batches.router, "KITCHEN"),
    ("kitchen_routes", kitchen_routes.router, "KITCHEN"),
    ("kitchen_dashboard", kitchen_dashboard.router, "KITCHEN"),
    ("ngo", ngo.router, "NGO"),
    ("ngo_pickups", ngo_pickups.router, "NGO"),
]
PUBLIC_ROUTERS = [("public", public.router), ("public_records", public_records.router)]
REAL_ROUTERS = [auth.router, me.router, health.router]  # these already have their endpoints

EXPECTED_PREFIX = {"ADMIN": "/api/admin", "KITCHEN": "/api/kitchen", "NGO": "/api/ngo"}


def probe_path(prefix: str, name: str) -> str:
    return f"{prefix}/_probe/{name}"


def probe_copy(router: APIRouter, name: str) -> APIRouter:
    """Same prefix and same role/CSRF dependencies as `router`, plus GET/POST/PUT/DELETE probes."""
    copy = APIRouter(prefix=router.prefix, dependencies=list(router.dependencies))

    def ok() -> dict:
        return {"ok": True}

    copy.add_api_route(f"/_probe/{name}", ok, methods=["GET", "POST", "PUT", "DELETE"])
    return copy


def make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-only-secret", session_cookie="annamsetu_session")
    install_error_handlers(app)
    for router in REAL_ROUTERS:
        app.include_router(router)
    for name, router, _role in ROLE_ROUTERS:
        app.include_router(probe_copy(router, name))
    for name, router in PUBLIC_ROUTERS:
        app.include_router(probe_copy(router, name))
    return app


@pytest.fixture
def app() -> FastAPI:
    return make_app()


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def log_in_as(app: FastAPI, role: str) -> None:
    user = CurrentUser(id=1, role=role, kitchen_id=1 if role == "KITCHEN" else None,
                       ngo_id=1 if role == "NGO" else None)
    app.dependency_overrides[current_user] = lambda: user


def csrf_token(client: TestClient) -> str:
    res = client.get("/api/auth/csrf")
    assert res.status_code == 200
    return res.json()["csrfToken"]


def assert_problem(res, status: int, code: str) -> None:
    assert res.status_code == status, res.text
    assert res.headers["content-type"].startswith("application/problem+json")
    body = res.json()
    assert PROBLEM_KEYS <= body.keys()
    assert body["status"] == status
    assert body["code"] == code


# ---------------------------------------------------------------- router configuration

def test_every_api_router_is_classified():
    classified = {id(r) for _n, r, _role in ROLE_ROUTERS} | {id(r) for _n, r in PUBLIC_ROUTERS} \
        | {id(r) for r in REAL_ROUTERS}
    missing = [r.prefix for r in main.API_ROUTERS if id(r) not in classified]
    assert missing == []


@pytest.mark.parametrize("name, router, role", ROLE_ROUTERS)
def test_role_router_prefix_matches_role(name, router, role):
    assert router.prefix.startswith(EXPECTED_PREFIX[role])


# ---------------------------------------------------------------- 401 / 403 per prefix

@pytest.mark.parametrize("name, router, role", ROLE_ROUTERS)
def test_role_router_needs_login(client, name, router, role):
    res = client.get(probe_path(router.prefix, name))
    assert_problem(res, 401, "NOT_LOGGED_IN")


@pytest.mark.parametrize("name, router, role", ROLE_ROUTERS)
def test_role_router_rejects_other_roles(app, client, name, router, role):
    for other in ROLES:
        if other == role:
            continue
        log_in_as(app, other)
        res = client.get(probe_path(router.prefix, name))
        assert_problem(res, 403, "FORBIDDEN")


@pytest.mark.parametrize("name, router, role", ROLE_ROUTERS)
def test_role_router_allows_its_role(app, client, name, router, role):
    log_in_as(app, role)
    res = client.get(probe_path(router.prefix, name))
    assert res.status_code == 200
    assert res.json() == {"ok": True}


@pytest.mark.parametrize("name, router", PUBLIC_ROUTERS)
def test_public_router_needs_no_login(client, name, router):
    assert client.get(probe_path(router.prefix, name)).status_code == 200


def test_me_needs_login(client):
    assert_problem(client.get("/api/me"), 401, "NOT_LOGGED_IN")


# ---------------------------------------------------------------- CSRF on unsafe methods

@pytest.mark.parametrize("name, router, role", ROLE_ROUTERS)
@pytest.mark.parametrize("method", UNSAFE_METHODS)
def test_role_router_unsafe_methods_need_csrf(app, client, name, router, role, method):
    log_in_as(app, role)
    path = probe_path(router.prefix, name)
    assert_problem(client.request(method, path), 403, "CSRF_INVALID")
    token = csrf_token(client)
    assert_problem(client.request(method, path, headers={"X-CSRF-Token": token + "x"}), 403, "CSRF_INVALID")
    assert client.request(method, path, headers={"X-CSRF-Token": token}).status_code == 200


@pytest.mark.parametrize("name, router", PUBLIC_ROUTERS)
@pytest.mark.parametrize("method", UNSAFE_METHODS)
def test_public_router_unsafe_methods_need_csrf(client, name, router, method):
    path = probe_path(router.prefix, name)
    assert_problem(client.request(method, path), 403, "CSRF_INVALID")
    token = csrf_token(client)
    assert client.request(method, path, headers={"X-CSRF-Token": token}).status_code == 200


def test_login_needs_csrf(client):
    res = client.post("/api/auth/login", data={"username": "kitchen", "password": "whatever-pass"})
    assert_problem(res, 403, "CSRF_INVALID")


def test_csrf_endpoint_sets_readable_cookie(client):
    res = client.get("/api/auth/csrf")
    token = res.json()["csrfToken"]
    assert res.cookies.get("XSRF-TOKEN") == token
    set_cookie = res.headers.get_list("set-cookie")
    xsrf = next(c for c in set_cookie if c.startswith("XSRF-TOKEN="))
    assert "httponly" not in xsrf.lower()  # api.js must be able to read it
    assert "samesite=lax" in xsrf.lower()
    # the same session keeps the same token
    assert csrf_token(client) == token


# ---------------------------------------------------------------- problem+json shape

def test_unknown_api_path_is_problem_404():
    res = TestClient(main.app).get("/api/does-not-exist")
    assert_problem(res, 404, "HTTP_404")
    assert res.json()["instance"] == "/api/does-not-exist"


def test_wrong_method_is_problem_405(client):
    res = client.post("/api/health")
    assert_problem(res, 405, "HTTP_405")


def test_bad_input_is_problem_400_without_echoing_values(client):
    token = csrf_token(client)
    res = client.post("/api/auth/login", data={"username": "kitchen"}, headers={"X-CSRF-Token": token})
    assert_problem(res, 400, "VALIDATION_FAILED")
    errors = res.json()["errors"]
    assert errors and all("input" not in err for err in errors)


# ---------------------------------------------------------------- login / logout / me flow (fake DB)

class FakeDb:
    """Just enough of a Session for current_user and me_view."""

    def __init__(self, *rows):
        self.rows = {(type(r), r.id): r for r in rows}

    def get(self, model, key):
        return self.rows.get((model, key))

    def close(self):
        pass


@pytest.fixture
def kitchen_account(app, monkeypatch):
    user = AppUser(id=7, username="cook", password_hash=password_hash.hash("right-password"),
                   display_name="Test Cook", role="KITCHEN", kitchen_id=None, ngo_id=None, enabled=True)
    fake = FakeDb(user)
    app.dependency_overrides[get_db] = lambda: fake
    monkeypatch.setattr(users, "find_by_username", lambda db, name: user if name == "cook" else None)
    return user


def login(client: TestClient, username: str, password: str):
    token = csrf_token(client)
    return client.post("/api/auth/login", data={"username": username, "password": password},
                       headers={"X-CSRF-Token": token})


def test_login_me_logout_flow(client, kitchen_account):
    before = csrf_token(client)
    res = login(client, "cook", "right-password")
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == "KITCHEN"
    assert body["displayName"] == "Test Cook"
    new_token = body["csrfToken"]
    assert new_token != before  # login issues a new CSRF token
    assert client.cookies.get("XSRF-TOKEN") == new_token

    me_res = client.get("/api/me")
    assert me_res.status_code == 200
    me_body = me_res.json()
    assert me_body["username"] == "cook"
    assert me_body["role"] == "KITCHEN"
    assert me_body["sampleData"] is False
    assert me_body["serverNow"].endswith("+05:30")

    # the old token no longer works
    assert_problem(client.post("/api/auth/logout", headers={"X-CSRF-Token": before}), 403, "CSRF_INVALID")
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": new_token}).status_code == 204
    assert_problem(client.get("/api/me"), 401, "NOT_LOGGED_IN")


def test_login_with_wrong_password(client, kitchen_account):
    assert_problem(login(client, "cook", "wrong-password"), 401, "BAD_CREDENTIALS")


def test_login_with_unknown_user(client, kitchen_account):
    assert_problem(login(client, "nobody", "right-password"), 401, "BAD_CREDENTIALS")


def test_login_with_password_over_72_bytes_is_bad_credentials(client, kitchen_account):
    assert_problem(login(client, "cook", "x" * 73), 401, "BAD_CREDENTIALS")


def test_disabled_user_cannot_log_in_or_use_session(client, kitchen_account):
    assert login(client, "cook", "right-password").status_code == 200
    kitchen_account.enabled = False
    assert_problem(client.get("/api/me"), 401, "NOT_LOGGED_IN")
    assert_problem(login(client, "cook", "right-password"), 401, "BAD_CREDENTIALS")


def test_logout_needs_csrf_too(client, kitchen_account):
    assert login(client, "cook", "right-password").status_code == 200
    assert_problem(client.post("/api/auth/logout"), 403, "CSRF_INVALID")
    assert client.get("/api/me").status_code == 200  # still logged in


def test_logout_ends_the_token_and_the_next_page_gets_a_new_one(client, kitchen_account):
    token_after_login = login(client, "cook", "right-password").json()["csrfToken"]
    res = client.post("/api/auth/logout", headers={"X-CSRF-Token": token_after_login})
    assert res.status_code == 204
    set_cookie = " | ".join(res.headers.get_list("set-cookie")).lower()
    assert 'xsrf-token=""' in set_cookie and "max-age=0" in set_cookie  # the readable token cookie is deleted
    assert "annamsetu_session=null" in set_cookie  # the session cookie is expired

    new_token = csrf_token(client)  # what api.js does after logout
    assert new_token != token_after_login
    res = client.post("/api/auth/login", data={"username": "cook", "password": "right-password"},
                      headers={"X-CSRF-Token": token_after_login})
    assert_problem(res, 403, "CSRF_INVALID")  # the old token is dead


# ---------------------------------------------------------------- password checks: timing and bcrypt's 72 bytes

class SpyHasher:
    """Stands in for users.password_hash and records which stored hash each verify() was given."""

    def __init__(self):
        self.checked: list[str] = []

    def verify(self, password: str, stored_hash: str) -> bool:
        self.checked.append(stored_hash)
        return password_hash.verify(password, stored_hash)


@pytest.fixture
def spy(monkeypatch) -> SpyHasher:
    hasher = SpyHasher()
    monkeypatch.setattr(users, "password_hash", hasher)
    return hasher


def test_known_user_checks_their_own_hash(client, kitchen_account, spy):
    assert_problem(login(client, "cook", "wrong-password"), 401, "BAD_CREDENTIALS")
    assert spy.checked == [kitchen_account.password_hash]


def test_unknown_user_still_runs_one_bcrypt_check_on_the_dummy_hash(client, kitchen_account, spy):
    # The same bcrypt work as for a real user, so the response time does not reveal which usernames exist.
    assert_problem(login(client, "nobody", "right-password"), 401, "BAD_CREDENTIALS")
    assert spy.checked == [dummy_hash()]


def test_disabled_user_still_runs_one_bcrypt_check_on_the_dummy_hash(client, kitchen_account, spy):
    kitchen_account.enabled = False
    assert_problem(login(client, "cook", "right-password"), 401, "BAD_CREDENTIALS")
    assert spy.checked == [dummy_hash()]


@pytest.mark.parametrize("password", [
    "x" * 73,       # 73 bytes
    "அ" * 25,  # 25 Tamil letters: only 25 characters, but 75 bytes in UTF-8
])
def test_password_over_72_bytes_never_reaches_bcrypt(client, kitchen_account, spy, password):
    assert_problem(login(client, "cook", password), 401, "BAD_CREDENTIALS")
    assert spy.checked == []


def test_a_72_byte_password_still_works(client, monkeypatch):
    password = "p" * 72
    user = AppUser(id=8, username="long", password_hash=password_hash.hash(password), display_name="Long",
                   role="ADMIN", kitchen_id=None, ngo_id=None, enabled=True)
    monkeypatch.setattr(users, "find_by_username", lambda db, name: user if name == "long" else None)
    client.app.dependency_overrides[get_db] = lambda: FakeDb(user)
    assert login(client, "long", password).status_code == 200


def test_bcrypt_itself_rejects_more_than_72_bytes():
    # Why the 72-byte rule exists: bcrypt 5 raises instead of silently truncating.
    with pytest.raises(ValueError):
        password_hash.hash("x" * 73)
    with pytest.raises(ValueError):
        password_hash.verify("x" * 73, dummy_hash())


# ---------------------------------------------------------------- the real app: every route carries its prefix rule

def dependency_calls(dependant) -> set:
    """Every dependency function a route runs, including the dependencies of dependencies."""
    calls = set()
    for sub in dependant.dependencies:
        calls.add(sub.call)
        calls |= dependency_calls(sub)
    return calls


def test_every_real_api_route_carries_its_prefix_rule():
    """Guards later phases: an endpoint added under /api/kitchen without the KITCHEN rule (or without CSRF)
    fails here. (FastAPI 0.162 keeps included routers whole; iter_route_contexts lists their endpoints.)"""
    routes = [r for r in iter_route_contexts(main.app.routes + demo_router.router.routes)
              if isinstance(r.original_route, APIRoute) and r.path.startswith("/api/")]
    paths = {r.path for r in routes}
    assert {"/api/auth/csrf", "/api/auth/login", "/api/auth/logout", "/api/me", "/api/health",
            "/api/admin/demo/clock", "/api/admin/demo/reset"} <= paths
    for route in routes:
        calls = dependency_calls(route.dependant)
        for prefix, role_dependency in (("/api/admin", admin_user), ("/api/kitchen", kitchen_user),
                                        ("/api/ngo", ngo_user)):
            if route.path.startswith(prefix + "/"):
                assert role_dependency in calls, route.path
        if route.path == "/api/me":
            assert current_user in calls
        if route.path == "/api/health":
            assert route.methods <= {"GET", "HEAD"}  # public and read-only: no CSRF needed
        else:
            assert csrf_protect in calls, route.path


def test_real_session_cookie_settings():
    session = next(m for m in main.app.user_middleware if m.cls is SessionMiddleware)
    assert session.kwargs["session_cookie"] == "annamsetu_session"
    assert session.kwargs["same_site"] == "lax"
    assert session.kwargs["max_age"] == 12 * 3600  # 12 h from login
    assert session.kwargs["https_only"] == get_settings().secure_cookies  # Secure in prod
    assert session.kwargs["secret_key"] == get_settings().secret_key


def test_xsrf_cookie_is_secure_when_secure_cookies_is_on(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "secure_cookies", True)
    res = client.get("/api/auth/csrf")
    xsrf = next(c for c in res.headers.get_list("set-cookie") if c.startswith("XSRF-TOKEN="))
    assert "secure" in xsrf.lower()
    assert "httponly" not in xsrf.lower()
