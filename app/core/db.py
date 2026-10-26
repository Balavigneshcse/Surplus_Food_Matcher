"""Database engine, session factory and the declarative Base for all models."""
from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# The connection time zone is UTC, so timestamptz values come back as aware UTC datetimes.
# (The integration tests build their engine with the same arguments.)
UTC_CONNECT_ARGS = {"options": "-c timezone=UTC"}

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args=UTC_CONNECT_ARGS,
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    # Every Mapped[datetime] column becomes a timestamptz.
    type_annotation_map = {datetime: DateTime(timezone=True)}


def get_db():
    # Closing the session without commit() rolls back, so an ApiError undoes any change.
    with SessionLocal() as db:
        yield db


DbSession = Annotated[Session, Depends(get_db)]
