"""Demo mode end to end: the seeded users log in, /api/me shows SAMPLE DATA, the demo router is ADMIN-only
and needs CSRF, and POST /api/admin/demo/reset works over HTTP (TRUNCATE despite the probe-log trigger).

main.app was built with APP_DEMO=false, so this test assembles the same pieces with the demo router.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from app import main
from app.core.clock import IST, get_clock, use_clock
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import install_error_handlers
from app.demo import router as demo_router
from app.demo.clock import DemoClock
from app.demo.seeder import seed_demo
from app.models import Kitchen, OptOut

pytestmark = pytest.mark.integration

PASSWORDS = {"admin": "admin-test-pass", "kitchen": "kitchen-test-pass", "ngo": "ngo-test-pass"}


@pytest.fixture
def demo_clock(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "demo", True)
    for username, password in PASSWORDS.items():
        monkeypatch.setattr(settings, f"demo_{username}_password", password)
    previous = get_clock()
    clock = DemoClock()
    use_clock(clock)
    with SessionLocal() as db:
        seed_demo(db, clock)
    yield clock
    use_clock(previous)


@pytest.fixture
def client(demo_clock) -> TestClient:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-only-secret", session_cookie="annamsetu_session")
    install_error_handlers(app)
    for router in main.API_ROUTERS:
        app.include_router(router)
    app.include_router(demo_router.router)
    return TestClient(app)


def log_in(client: TestClient, username: str) -> str:
    """Log in as a demo user and return the new CSRF token."""
    token = client.get("/api/auth/csrf").json()["csrfToken"]
    res = client.post("/api/auth/login", data={"username": username, "password": PASSWORDS[username]},
                      headers={"X-CSRF-Token": token})
    assert res.status_code == 200, res.text
    return res.json()["csrfToken"]


@pytest.mark.parametrize("username, role, place", [
    ("admin", "ADMIN", None),
    ("kitchen", "KITCHEN", "Sample Hostel Mess"),
    ("ngo", "NGO", "Sample NGO A"),
])
def test_each_demo_user_logs_in_and_sees_sample_data(client, username, role, place):
    log_in(client, username)
    me = client.get("/api/me").json()
    assert me["role"] == role
    assert me["sampleData"] is True
    assert (me["kitchenName"] or me["ngoName"]) == place


@pytest.mark.parametrize("username", ["kitchen", "ngo"])
def test_other_roles_get_403_on_the_demo_router(client, username):
    log_in(client, username)
    res = client.get("/api/admin/demo/clock")
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


def test_demo_router_needs_login(client):
    assert client.get("/api/admin/demo/clock").json()["code"] == "NOT_LOGGED_IN"


def test_admin_jumps_the_clock_only_with_csrf(client, demo_clock):
    token = log_in(client, "admin")
    assert client.post("/api/admin/demo/clock", json={"plusMinutes": 15}).json()["code"] == "CSRF_INVALID"
    res = client.post("/api/admin/demo/clock", json={"plusMinutes": 15}, headers={"X-CSRF-Token": token})
    assert res.status_code == 200
    assert res.json()["offsetMinutes"] == 15


def test_admin_resets_the_demo_over_http(client, demo_clock):
    token = log_in(client, "admin")
    with SessionLocal() as db:
        db.add(OptOut(kitchen_id=db.scalar(select(Kitchen.id)), slot="LUNCH", meal_date=demo_clock.today(),
                      hostel_id="EXTRA-1"))
        db.commit()

    res = client.post("/api/admin/demo/reset", headers={"X-CSRF-Token": token})
    assert res.status_code == 200, res.text
    assert res.json()["serverNow"][11:16] == "08:30"
    assert demo_clock.now().astimezone(IST).strftime("%H:%M") == "08:30"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(OptOut)) == 44  # the extra row is gone
    # the admin's session survives a reset (users are not truncated)
    assert client.get("/api/me").json()["role"] == "ADMIN"
