"""The app starts and stops cleanly, with the scheduler hook on, serves the static pages, and answers
unknown /api paths with problem+json."""
import pytest
from fastapi.testclient import TestClient

from app import main, scheduler
from app.core.config import get_settings
from app.core.security import dummy_hash


def test_lifespan_starts_and_stops_the_scheduler(monkeypatch):
    monkeypatch.setattr(get_settings(), "scheduler_enabled", True)
    with TestClient(main.app) as client:
        res = client.get("/login.html")
        assert res.status_code == 200
        assert "<title>AnnamSetu login</title>" in res.text
    # leaving the block ran the shutdown half of lifespan without errors


class FakeScheduler:
    """Records what lifespan asks of APScheduler, without starting a thread."""
    created: list["FakeScheduler"] = []

    def __init__(self, timezone):
        self.timezone = timezone
        self.jobs = {}
        self.started = self.stopped = False
        FakeScheduler.created.append(self)

    def add_job(self, func, trigger, id, **options):
        self.jobs[id] = (func, trigger, options)

    def start(self):
        self.started = True

    def shutdown(self, wait=True):
        self.stopped = True


def test_lifespan_registers_the_tick_and_the_nightly_purge(monkeypatch):
    monkeypatch.setattr(get_settings(), "scheduler_enabled", True)
    monkeypatch.setattr(main, "BackgroundScheduler", FakeScheduler)
    FakeScheduler.created.clear()
    with TestClient(main.app):
        fake = FakeScheduler.created[-1]
        assert fake.started and not fake.stopped
    assert fake.stopped
    assert fake.timezone == "Asia/Kolkata"

    func, trigger, options = fake.jobs["loop-tick"]
    assert (func, trigger) == (scheduler.loop_tick, "interval")
    # every APP_TICK_SECONDS (15 by default); never two ticks at once
    assert options == {"seconds": get_settings().tick_seconds, "max_instances": 1, "coalesce": True}

    func, trigger, options = fake.jobs["purge-opt-outs"]
    assert (func, trigger, options) == (scheduler.purge_old_opt_outs, "cron", {"hour": 2, "minute": 30})


def test_no_scheduler_when_disabled(monkeypatch):
    monkeypatch.setattr(main, "BackgroundScheduler", FakeScheduler)
    FakeScheduler.created.clear()
    with TestClient(main.app):  # tests/conftest.py sets APP_SCHEDULER_ENABLED=false
        pass
    assert FakeScheduler.created == []


class FakeSession:
    """Stands in for SessionLocal(): counts the sessions the tick opens."""
    opened = 0

    def __enter__(self):
        FakeSession.opened += 1
        return self

    def __exit__(self, *exc):
        return False


def test_steps_1_and_2_are_wired_in_the_plan_order():
    assert [name for name, _find, _handle in scheduler.STEPS] == ["issue-at-cutoff", "start-service"]
    from app.services import meals
    assert scheduler.STEPS[0][1:] == (meals.find_past_cutoff, meals.auto_issue)
    assert scheduler.STEPS[1][1:] == (meals.find_past_start, meals.start_service)


def test_loop_tick_gives_each_item_its_own_session_and_survives_failures(monkeypatch):
    calls = []

    def find_two(db, now):
        return [1, 2]

    def handle(db, item_id, now):
        calls.append(item_id)
        if item_id == 1:
            raise RuntimeError("one bad row")

    def find_broken(db, now):
        raise RuntimeError("database down")

    monkeypatch.setattr(scheduler, "SessionLocal", FakeSession)
    monkeypatch.setattr(scheduler, "STEPS", [("broken", find_broken, handle), ("two", find_two, handle)])
    FakeSession.opened = 0
    scheduler.loop_tick(now=None)
    assert calls == [1, 2]  # the failing item and the failing step did not stop the rest
    assert FakeSession.opened == 4  # broken find + one find + one session per item


def test_root_serves_index_page():
    res = TestClient(main.app).get("/")
    assert res.status_code == 200
    assert "<title>AnnamSetu</title>" in res.text


def test_docs_are_enabled_in_test_settings():
    assert TestClient(main.app).get("/openapi.json").status_code == 200


def test_startup_prepares_the_dummy_hash():
    """Made at startup, so the first login with an unknown username costs the same as any other."""
    dummy_hash.cache_clear()
    with TestClient(main.app):
        assert dummy_hash.cache_info().currsize == 1


# ---------------------------------------------------------------- static pages and unknown paths

@pytest.mark.parametrize("path, content_type", [
    ("/index.html", "text/html"),
    ("/login.html", "text/html"),
    ("/css/app.css", "text/css"),
    ("/css/print.css", "text/css"),
    ("/js/api.js", "javascript"),
    ("/js/ui.js", "javascript"),
    ("/js/i18n.js", "javascript"),
    ("/vendor/chart.umd.min.js", "javascript"),
])
def test_static_files_are_served_without_login(path, content_type):
    res = TestClient(main.app).get(path)
    assert res.status_code == 200
    assert content_type in res.headers["content-type"]


@pytest.mark.parametrize("method", ["GET", "HEAD", "POST", "PUT", "DELETE"])
def test_unknown_api_path_is_problem_404_for_every_method(method):
    res = TestClient(main.app).request(method, "/api/kitchen/no-such-thing")
    assert res.status_code == 404
    if method != "HEAD":
        assert res.headers["content-type"].startswith("application/problem+json")
        assert res.json()["code"] == "HTTP_404"
        assert res.json()["instance"] == "/api/kitchen/no-such-thing"


@pytest.mark.parametrize("method, path, allow", [
    ("POST", "/api/health", "GET"),
    ("DELETE", "/api/me", "GET"),
    ("GET", "/api/auth/login", "POST"),
])
def test_known_api_path_with_the_wrong_method_is_problem_405(method, path, allow):
    res = TestClient(main.app).request(method, path)
    assert res.status_code == 405
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["code"] == "HTTP_405"
    assert res.headers["allow"] == allow


def test_unknown_page_is_problem_404():
    res = TestClient(main.app).get("/no-such-page.html")
    assert res.status_code == 404
    assert res.json()["code"] == "HTTP_404"
