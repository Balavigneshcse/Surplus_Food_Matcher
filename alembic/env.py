"""Alembic environment. The database URL comes from app Settings unless a test sets sqlalchemy.url."""
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

import app.models  # noqa: F401  (models/__init__.py imports every model module)
from app.core.config import get_settings
from app.core.db import Base

config = context.config

# Set up logging from alembic.ini, without silencing the app's own loggers.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata  # used only by --autogenerate drafts
URL = config.get_main_option("sqlalchemy.url") or get_settings().database_url  # tests set the first


def run_migrations_offline() -> None:
    """Write the SQL to stdout instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
