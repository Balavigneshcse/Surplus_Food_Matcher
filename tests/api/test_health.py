"""GET /api/health: public, GET only, and 503 problem+json when the database is down (no real DB needed)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.db import get_db
from app.core.errors import install_error_handlers
from app.routers import health


class FakeDb:
    def __init__(self, up: bool):
        self.up = up

    def execute(self, statement):
        if not self.up:
            raise OperationalError("select 1", {}, Exception("connection refused"))


def client_with(db: FakeDb) -> TestClient:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(health.router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_health_ok_needs_no_login():
    res = client_with(FakeDb(up=True)).get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert (body["status"], body["db"]) == ("ok", "ok")
    assert body["serverNow"].endswith("+05:30")


def test_health_is_503_when_the_database_is_down():
    res = client_with(FakeDb(up=False)).get("/api/health")
    assert res.status_code == 503
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["code"] == "DB_UNAVAILABLE"
    assert "connection refused" not in res.text  # no internals leak
