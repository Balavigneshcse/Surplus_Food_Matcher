"""The problem+json handlers for database errors (409) and unexpected errors (500)."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import ApiError, constraint_code, install_error_handlers


def integrity_error(constraint: str | None) -> IntegrityError:
    orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint))
    return IntegrityError("INSERT ...", {}, orig)


@pytest.mark.parametrize("constraint, code", [
    ("ck_cattle_raw_veg_only", "CATTLE_FEED_RAW_VEG_ONLY"),
    ("ux_offer_one_taker", "OFFER_NOT_OPEN"),
    ("ux_meal_one_reserve", "ONE_RESERVE_DISH"),
    ("ck_landfill_reason", "LANDFILL_NEEDS_REASON"),
    ("some_unknown_constraint", "CONSTRAINT_VIOLATED"),
    (None, "CONSTRAINT_VIOLATED"),
])
def test_constraint_name_maps_to_code(constraint, code):
    assert constraint_code(integrity_error(constraint))[0] == code


def make_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/integrity")
    def raise_integrity():
        raise integrity_error("ck_cattle_raw_veg_only")

    @app.get("/stale")
    def raise_stale():
        raise StaleDataError("UPDATE statement on table 'meal' expected to update 1 row(s); 0 were matched.")

    @app.get("/api-error")
    def raise_api_error():
        raise ApiError(409, "SAFECLOCK_NOT_GREEN", "The reserve is no longer GREEN")

    @app.get("/boom")
    def boom():
        raise RuntimeError("unexpected")

    return app


@pytest.fixture
def client():
    return TestClient(make_app(), raise_server_exceptions=False)


def test_integrity_error_is_409_with_code(client):
    res = client.get("/integrity")
    assert res.status_code == 409
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["code"] == "CATTLE_FEED_RAW_VEG_ONLY"


def test_stale_data_is_409_concurrent_edit(client):
    res = client.get("/stale")
    assert res.status_code == 409
    assert res.json()["code"] == "CONCURRENT_EDIT"


def test_api_error_keeps_status_and_code(client):
    res = client.get("/api-error")
    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "SAFECLOCK_NOT_GREEN"
    assert body["title"] == "Conflict"
    assert body["instance"] == "/api-error"


def test_unexpected_error_is_problem_500(client):
    res = client.get("/boom")
    assert res.status_code == 500
    assert res.json()["code"] == "INTERNAL_ERROR"
    assert "unexpected" not in res.text  # no internals leak to the client
