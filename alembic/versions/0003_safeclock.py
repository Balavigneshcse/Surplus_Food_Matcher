"""safeclock: reserve_batch, probe_reading (append-only)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reserve_batch",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("meal_id", sa.BigInteger, sa.ForeignKey("meal.id"), nullable=False),
        sa.Column("meal_dish_id", sa.BigInteger, sa.ForeignKey("meal_dish.id"), nullable=False),
        sa.Column("batch_no", sa.String(30), nullable=False),
        sa.Column("food_name", sa.String(100), nullable=False),
        sa.Column("is_veg", sa.Boolean, nullable=False),
        sa.Column("planned_g", sa.Integer, nullable=False),
        sa.Column("lidded_weight_g", sa.Integer),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lidded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'HOLDING'")),
        sa.Column("worst_colour", sa.String(5), nullable=False, server_default=sa.text("'GREEN'")),
        sa.Column("accepted_ngo_id", sa.BigInteger, sa.ForeignKey("ngo.id")),
        sa.Column("pickup_at", sa.DateTime(timezone=True)),
        sa.Column("dispose_reason", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("meal_id", name="uq_reserve_batch_meal"),  # one vessel per meal
        sa.UniqueConstraint("batch_no", name="uq_reserve_batch_batch_no"),
        sa.CheckConstraint("status in ('HOLDING', 'OFFERED', 'ACCEPTED', 'HANDED_OVER', 'USED_FOR_STUDENTS',"
                           " 'TO_DISPOSE', 'ROUTED')", name="ck_reserve_batch_status"),
        sa.CheckConstraint("worst_colour in ('GREEN', 'AMBER', 'RED')", name="ck_reserve_batch_worst_colour"),
        sa.CheckConstraint("planned_g >= 0", name="ck_reserve_batch_planned_g"),
        sa.CheckConstraint("lidded_weight_g is null or lidded_weight_g > 0", name="ck_reserve_batch_lidded_weight"),
    )
    op.execute("alter table reserve_batch add constraint ck_reserve_batch_prepared_before_lid"
               " check (prepared_at <= lidded_at)")
    op.execute("alter table reserve_batch add constraint ck_reserve_batch_accepted_has_ngo"
               " check (status not in ('ACCEPTED', 'HANDED_OVER') or accepted_ngo_id is not null)")
    op.execute("alter table reserve_batch add constraint ck_reserve_batch_dispose_reason"
               " check (status <> 'TO_DISPOSE' or dispose_reason is not null)")

    op.create_table(
        "probe_reading",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("batch_id", sa.BigInteger, sa.ForeignKey("reserve_batch.id"), nullable=False),
        sa.Column("temp_c", sa.Numeric(4, 1), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("recorded_by", sa.BigInteger, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("note", sa.Text),
        sa.CheckConstraint("temp_c between -10 and 120", name="ck_probe_temp_range"),
        sa.CheckConstraint("kind in ('LID', 'ROUTINE', 'HANDOVER')", name="ck_probe_kind"),
    )
    op.create_index("ix_probe_batch_read_at", "probe_reading", ["batch_id", "read_at"])
    # The probe log is evidence: no edits, no deletes. A correction is a new reading with a note.
    op.execute("""create function forbid_change() returns trigger language plpgsql as
                  $$ begin raise exception using message = tg_table_name || ' is append-only'; end $$""")
    op.execute("""create trigger probe_reading_append_only before update or delete on probe_reading
                  for each row execute function forbid_change()""")


def downgrade() -> None:
    op.execute("drop trigger probe_reading_append_only on probe_reading")
    op.execute("drop function forbid_change()")
    op.drop_index("ix_probe_batch_read_at", table_name="probe_reading")
    op.drop_table("probe_reading")
    op.drop_table("reserve_batch")
