"""In demo mode the app seeds the sample data when it starts (lifespan), and starting twice changes nothing."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import main
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import AppUser, Kitchen, Meal

pytestmark = pytest.mark.integration


@pytest.fixture
def demo_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "demo", True)
    monkeypatch.setattr(settings, "demo_admin_password", "admin-test-pass")
    monkeypatch.setattr(settings, "demo_kitchen_password", "kitchen-test-pass")
    monkeypatch.setattr(settings, "demo_ngo_password", "ngo-test-pass")


def counts() -> tuple[int, int, int]:
    with SessionLocal() as db:
        return tuple(db.scalar(select(func.count()).select_from(m)) for m in (Kitchen, AppUser, Meal))


def test_startup_seeds_the_demo_data_once(demo_settings):
    assert counts() == (0, 0, 0)
    with TestClient(main.app) as client:
        assert client.get("/api/health").json()["db"] == "ok"
    assert counts() == (1, 3, 2)
    with TestClient(main.app):  # a restart is idempotent
        pass
    assert counts() == (1, 3, 2)
    with SessionLocal() as db:
        assert db.scalar(select(Kitchen.name).where(Kitchen.code == "MESS1")) == "Sample Hostel Mess"


def test_startup_does_not_seed_outside_demo_mode():
    with TestClient(main.app):
        pass
    assert counts() == (0, 0, 0)
