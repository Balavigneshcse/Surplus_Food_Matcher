"""Settings: APP_ environment variables, the plan's default operating numbers (section 11.3)."""
from app.core.config import Settings


def make_settings(monkeypatch, **env) -> Settings:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)  # ignore the developer's .env


def test_operating_numbers_have_the_plan_defaults(monkeypatch):
    s = make_settings(monkeypatch)
    assert (s.tick_seconds, s.offer_timeout_min, s.max_overflow_offers, s.t90_lead_min) == (15, 10, 3, 90)
    assert (s.on_time_grace_min, s.no_show_grace_min, s.optout_retention_days) == (15, 30, 30)
    assert s.public_base_url == "http://localhost:8000"


def test_values_come_from_app_prefixed_variables(monkeypatch):
    s = make_settings(monkeypatch, APP_DEMO="true", APP_TICK_SECONDS="5", APP_SECURE_COOKIES="true")
    assert s.demo is True
    assert s.tick_seconds == 5
    assert s.secure_cookies is True


def test_safe_defaults_without_any_flags(monkeypatch):
    for name in ("APP_DEMO", "APP_DOCS", "APP_SECURE_COOKIES", "APP_SCHEDULER_ENABLED", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert (s.env, s.demo, s.docs, s.scheduler_enabled) == ("dev", False, False, True)
