# tests/conftest.py: runs before any test imports the app; real environment variables beat .env
import os

os.environ.update(APP_ENV="test", APP_DEMO="false", APP_SCHEDULER_ENABLED="false",
                  APP_DOCS="true", APP_SECURE_COOKIES="false")
os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("APP_DATABASE_URL", "postgresql+psycopg://annamsetu:unused@localhost:5432/unused")  # never your dev DB
