"""Migrations: one head, upgrade/downgrade both work, and the models mirror the migrated schema exactly.

Alembic's compare_metadata finds differences in tables, columns, types, nullability, server defaults,
indexes, unique constraints and foreign keys. It does NOT look inside CHECK conditions or the WHERE of
a partial index, so two more tests compare those: each model CHECK / index is added to a temporary copy
of the migrated table, and Postgres prints both definitions in its own normalised form.
"""
import re

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, inspect, select, text

import app.models  # noqa: F401
from app.core.db import Base
from app.core.errors import CONSTRAINT_CODES

pytestmark = pytest.mark.integration

PARTIAL_UNIQUE_INDEXES = {"ux_meal_one_reserve", "ux_offer_one_pending", "ux_offer_one_taker"}


def test_there_is_exactly_one_head(alembic_cfg):
    assert len(ScriptDirectory.from_config(alembic_cfg).get_heads()) == 1


def test_head_is_0006(engine):
    with engine.connect() as conn:
        assert conn.scalar(text("select version_num from alembic_version")) == "0006"


def test_every_model_can_select(db):
    for mapper in Base.registry.mappers:
        db.execute(select(mapper.class_).limit(1))
    assert len(Base.metadata.tables) == 14


def test_models_match_migrations(engine):
    """Tables, columns, types, nullability, server defaults, indexes, uniques and foreign keys all agree."""
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True, "compare_server_default": True})
        differences = compare_metadata(ctx, Base.metadata)
    assert differences == []


# ---------------------------------------------------------------- CHECKs and indexes, compared by Postgres

def model_checks(table) -> list[CheckConstraint]:
    return [c for c in table.constraints if isinstance(c, CheckConstraint)]


def check_definitions(conn, table_name: str) -> dict[str, str]:
    rows = conn.execute(text("select conname, pg_get_constraintdef(oid) from pg_constraint"
                             " where conrelid = cast(:t as regclass) and contype = 'c'"), {"t": table_name})
    return dict(rows.all())


def index_definitions(conn, table_name: str, names: set[str]) -> dict[str, str]:
    rows = conn.execute(text("select indexname, indexdef from pg_indexes where tablename = :t"), {"t": table_name})
    # "CREATE INDEX ix ON public.offer USING ..." -> "CREATE INDEX ix ON <table> USING ..."
    return {name: re.sub(r" ON \S+ USING ", " ON <table> USING ", indexdef)
            for name, indexdef in rows.all() if name in names}


@pytest.fixture
def scratch(engine):
    """A connection whose work is always rolled back (temporary tables vanish with it)."""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            yield conn
        finally:
            trans.rollback()


def test_check_conditions_match_models(scratch):
    for table in Base.metadata.sorted_tables:
        copy = f"drift_{table.name}"
        scratch.execute(text(f"create temp table {copy} (like {table.name})"))  # columns only, no CHECKs
        for check in model_checks(table):
            scratch.execute(text(f"alter table {copy} add constraint {check.name} check ({check.sqltext})"))
        assert check_definitions(scratch, copy) == check_definitions(scratch, table.name), table.name


def test_index_columns_and_conditions_match_models(scratch):
    for table in Base.metadata.sorted_tables:
        if not table.indexes:
            continue
        copy = f"drift_{table.name}"
        scratch.execute(text(f"create temp table {copy} (like {table.name})"))
        for index in table.indexes:
            columns = ", ".join(column.name for column in index.columns)
            where = index.dialect_options["postgresql"]["where"]
            sql = f"create {'unique ' if index.unique else ''}index {index.name} on {copy} ({columns})"
            scratch.execute(text(sql + (f" where {where}" if where is not None else "")))
        names = {index.name for index in table.indexes}
        in_db = index_definitions(scratch, table.name, names)
        assert set(in_db) == names, table.name
        assert index_definitions(scratch, copy, names) == in_db, table.name


def test_partial_unique_indexes_and_trigger_exist(engine):
    with engine.connect() as conn:
        indexes = set(conn.scalars(text("select indexname from pg_indexes where schemaname = 'public'")))
        triggers = set(conn.scalars(text("select tgname from pg_trigger where not tgisinternal")))
    assert PARTIAL_UNIQUE_INDEXES <= indexes
    assert "probe_reading_append_only" in triggers


def test_every_id_is_a_bigint_generated_always_as_identity(engine):
    """Plan 5: ids are `bigint generated always as identity`; the seeder never sets them."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "select table_name, data_type, is_identity, identity_generation from information_schema.columns"
            " where table_schema = 'public' and column_name = 'id'")).all()
    assert {name for name, *_ in rows} == set(Base.metadata.tables)
    assert {tuple(rest) for _name, *rest in rows} == {("bigint", "YES", "ALWAYS")}


def test_every_timestamp_is_timestamptz(engine):
    """Plan 5: every timestamp is a timestamptz (stored as UTC); none is a naive `timestamp`."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "select table_name, column_name, data_type from information_schema.columns"
            " where table_schema = 'public' and table_name <> 'alembic_version'"
            " and (data_type in ('timestamp with time zone', 'timestamp without time zone')"
            " or right(column_name, 3) = '_at')")).all()
    assert rows  # created_at, read_at, sent_at, ...
    wrong = [(t, c, d) for t, c, d in rows if d != "timestamp with time zone"]
    assert wrong == []


def test_every_error_code_names_a_real_constraint(engine):
    """core/errors.py maps constraint names to codes; a typo there would silently become CONSTRAINT_VIOLATED."""
    with engine.connect() as conn:
        constraints = set(conn.scalars(text("select conname from pg_constraint")))
        indexes = set(conn.scalars(text("select indexname from pg_indexes where schemaname = 'public'")))
    assert set(CONSTRAINT_CODES) - (constraints | indexes) == set()


def test_downgrade_to_base_and_upgrade_again(alembic_cfg, engine):
    command.downgrade(alembic_cfg, "base")
    try:
        with engine.connect() as conn:
            assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
            assert conn.scalar(text("select count(*) from pg_proc where proname = 'forbid_change'")) == 0
    finally:
        command.upgrade(alembic_cfg, "head")  # leave the database at head for the other tests
    with engine.connect() as conn:
        assert set(Base.metadata.tables) <= set(inspect(conn).get_table_names())


def test_each_revision_downgrades_and_upgrades_one_step(alembic_cfg, engine):
    """Walk down one revision at a time (0006 -> base) and back up, so every downgrade() is exercised alone."""
    revisions = ["0006", "0005", "0004", "0003", "0002", "0001"]
    try:
        for revision in revisions:
            command.downgrade(alembic_cfg, "-1")
            with engine.connect() as conn:
                current = conn.scalar(text("select version_num from alembic_version"))
            expected = revisions[revisions.index(revision) + 1] if revision != "0001" else None
            assert current == expected
    finally:
        command.upgrade(alembic_cfg, "head")
