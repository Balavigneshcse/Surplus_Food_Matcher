"""Demo clock endpoints (ADMIN only, demo mode only). Reset is covered by the integration tests."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.core.clock import Clock, get_clock, use_clock
from app.core.errors import install_error_handlers
from app.core.security import CurrentUser, current_user
from app.demo import router as demo_router
from app.demo.clock import DemoClock
from app.routers import auth


@pytest.fixture
def demo_clock():
    previous = get_clock()
    clock = DemoClock()
    use_clock(clock)
    yield clock
    use_clock(previous)


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-only-secret")
    install_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(demo_router.router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(id=1, role="ADMIN", kitchen_id=None, ngo_id=None)
    test_client = TestClient(app)
    token = test_client.get("/api/auth/csrf").json()["csrfToken"]
    test_client.headers["X-CSRF-Token"] = token
    return test_client


def test_set_clock_to_an_ist_time(client, demo_clock):
    res = client.post("/api/admin/demo/clock", json={"at": "2026-10-30T11:55:00"})  # no offset = IST
    assert res.status_code == 200
    assert res.json()["serverNow"].startswith("2026-10-30T11:55:00")
    assert res.json()["serverNow"].endswith("+05:30")


def test_jump_and_reset(client, demo_clock):
    res = client.post("/api/admin/demo/clock", json={"plusMinutes": 30})
    assert res.json()["offsetMinutes"] == 30
    assert demo_clock.offset == timedelta(minutes=30)
    res = client.delete("/api/admin/demo/clock")
    assert res.json()["offsetMinutes"] == 0
    assert client.get("/api/admin/demo/clock").json()["offsetMinutes"] == 0


@pytest.mark.parametrize("body", [{}, {"at": "2026-10-30T11:55:00", "plusMinutes": 5}, {"plusMinutes": 5000}])
def test_clock_body_must_have_exactly_one_valid_field(client, demo_clock, body):
    res = client.post("/api/admin/demo/clock", json=body)
    assert res.status_code == 400
    assert res.json()["code"] == "VALIDATION_FAILED"


def test_clock_endpoints_refuse_outside_demo_mode(client):
    previous = get_clock()
    use_clock(Clock())
    try:
        res = client.get("/api/admin/demo/clock")
    finally:
        use_clock(previous)
    assert res.status_code == 409
    assert res.json()["code"] == "NOT_DEMO_MODE"


def test_demo_router_is_not_mounted_when_demo_is_off():
    from app import main
    res = TestClient(main.app).get("/api/admin/demo/clock")
    assert res.status_code == 404  # falls through to the static mount: no such page
    assert res.json()["code"] == "HTTP_404"
