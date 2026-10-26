"""App settings, read from environment variables and the .env file (prefix APP_)."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    demo: bool = False
    docs: bool = False
    secret_key: str
    database_url: str
    public_base_url: str = "http://localhost:8000"
    secure_cookies: bool = False
    scheduler_enabled: bool = True
    tick_seconds: int = 15
    offer_timeout_min: int = 10
    max_overflow_offers: int = 3
    t90_lead_min: int = 90
    on_time_grace_min: int = 15
    no_show_grace_min: int = 30
    hostel_id_pattern: str = r"^[A-Za-z0-9-]{3,20}$"
    # opt-out POSTs per client IP (in memory, one worker); a hostel Wi-Fi may share one IP, so be generous
    optout_rate_limit: int = 30
    optout_rate_window_s: int = 60
    optout_retention_days: int = 30
    demo_admin_password: str | None = None
    demo_kitchen_password: str | None = None
    demo_ngo_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
