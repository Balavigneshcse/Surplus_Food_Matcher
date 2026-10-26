# tests/integration/conftest.py: a throwaway postgres:17 (Testcontainers) migrated to head with Alembic.
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from testcontainers.community.postgres import PostgresContainer  # 4.15 path; testcontainers.postgres is deprecated

from app.core.db import UTC_CONNECT_ARGS, SessionLocal

PROJECT_DIR = Path(__file__).resolve().parents[2]
APP_TABLES = ("kitchen, ngo, partnership, app_user, meal_slot, dish, meal, meal_dish, opt_out, reserve_batch,"
              " probe_reading, offer, batch_record, route_log")


@pytest.fixture(scope="session")
def db_url():
    if os.getenv("TEST_DATABASE_URL"):  # CI: the workflow's postgres service
        yield os.environ["TEST_DATABASE_URL"]
    else:  # laptop: a throwaway postgres:17 container
        with PostgresContainer("postgres:17", driver="psycopg") as pg:
            yield pg.get_connection_url()


@pytest.fixture(scope="session")
def alembic_cfg(db_url) -> Config:
    cfg = Config(str(PROJECT_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture(scope="session")
def engine(db_url):
    test_engine = create_engine(db_url, connect_args=UTC_CONNECT_ARGS)  # the same UTC setting as the app
    yield test_engine
    test_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated(alembic_cfg, engine):
    command.upgrade(alembic_cfg, "head")
    SessionLocal.configure(bind=engine)  # the app's sessions now use the test database


@pytest.fixture(autouse=True)
def clean_db(engine):
    """Every test starts from empty tables and creates its own data."""
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {APP_TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def fresh_rate_limiter():
    """The opt-out rate limiter lives in memory; every test starts with no recorded requests."""
    from app.services.opt_outs import rate_limiter
    rate_limiter.clear()
    yield
    rate_limiter.clear()


@pytest.fixture
def clock():
    """The app clock, fixed at 08:30 IST on 30 Oct 2026 (tests move it with clock.at = ...)."""
    from app.core.clock import get_clock, use_clock
    from tests.integration.factories import FixedClock, at
    previous = get_clock()
    fixed = FixedClock(at(8, 30))
    use_clock(fixed)
    yield fixed
    use_clock(previous)


@pytest.fixture
def client():
    """The real app (all routers, error handlers, session middleware) talking to the test database."""
    from fastapi.testclient import TestClient
    from app import main
    return TestClient(main.app)
