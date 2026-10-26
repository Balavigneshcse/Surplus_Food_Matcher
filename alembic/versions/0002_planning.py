"""planning: meal_slot, dish, meal, meal_dish, opt_out

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SLOTS = "('BREAKFAST', 'LUNCH', 'DINNER')"


def upgrade() -> None:
    op.create_table(
        "meal_slot",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("kitchen_id", sa.BigInteger, sa.ForeignKey("kitchen.id"), nullable=False),
        sa.Column("slot", sa.String(10), nullable=False),
        sa.Column("service_start", sa.Time, nullable=False),
        sa.Column("service_end", sa.Time, nullable=False),
        sa.Column("optout_cutoff_min", sa.Integer, nullable=False, server_default=sa.text("180")),
        sa.Column("attendance_ratio", sa.Numeric(4, 3), nullable=False, server_default=sa.text("0.850")),
        sa.Column("buffer_pct", sa.Numeric(4, 1), nullable=False, server_default=sa.text("6.0")),
        sa.Column("share_arrived_by_t90", sa.Numeric(4, 3), nullable=False, server_default=sa.text("0.400")),
        sa.Column("standing_ngo_id", sa.BigInteger, sa.ForeignKey("ngo.id")),
        sa.Column("pickup_offset_min", sa.Integer, nullable=False, server_default=sa.text("15")),
        sa.Column("rescue_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("kitchen_id", "slot", name="uq_meal_slot_kitchen_slot"),
        sa.CheckConstraint(f"slot in {SLOTS}", name="ck_meal_slot_slot"),
        sa.CheckConstraint("attendance_ratio between 0 and 1", name="ck_meal_slot_ratio"),
        sa.CheckConstraint("share_arrived_by_t90 > 0 and share_arrived_by_t90 <= 1", name="ck_meal_slot_share_t90"),
        sa.CheckConstraint("buffer_pct >= 0", name="ck_meal_slot_buffer"),
        sa.CheckConstraint("optout_cutoff_min >= 0", name="ck_meal_slot_cutoff"),
        sa.CheckConstraint("pickup_offset_min >= 0", name="ck_meal_slot_pickup_offset"),
    )
    op.execute("alter table meal_slot add constraint ck_meal_slot_end_after_start"
               " check (service_end > service_start)")

    op.create_table(
        "dish",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("kitchen_id", sa.BigInteger, sa.ForeignKey("kitchen.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_ta", sa.String(100)),
        sa.Column("is_veg", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("cooked_g_per_diner", sa.Integer, nullable=False),
        sa.Column("raw_g_per_diner", sa.Integer),
        sa.Column("cost_per_kg_inr", sa.Numeric(8, 2)),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("kitchen_id", "name", name="uq_dish_kitchen_name"),
        sa.CheckConstraint("cooked_g_per_diner > 0", name="ck_dish_cooked_g"),
        sa.CheckConstraint("raw_g_per_diner is null or raw_g_per_diner > 0", name="ck_dish_raw_g"),
        sa.CheckConstraint("cost_per_kg_inr is null or cost_per_kg_inr >= 0", name="ck_dish_cost"),
    )

    op.create_table(
        "meal",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("kitchen_id", sa.BigInteger, sa.ForeignKey("kitchen.id"), nullable=False),
        sa.Column("meal_slot_id", sa.BigInteger, sa.ForeignKey("meal_slot.id"), nullable=False),
        sa.Column("meal_date", sa.Date, nullable=False),
        sa.Column("service_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'PLANNED'")),
        sa.Column("registered_count", sa.Integer, nullable=False),
        sa.Column("extra_opt_outs", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("opted_out_count", sa.Integer),
        sa.Column("attendance_ratio", sa.Numeric(4, 3), nullable=False),
        sa.Column("buffer_pct", sa.Numeric(4, 1), nullable=False),
        sa.Column("p50", sa.Integer),
        sa.Column("p90", sa.Integer),
        sa.Column("forecast_method", sa.String(10), nullable=False, server_default=sa.text("'RULE_V1'")),
        sa.Column("rule_p50", sa.Integer),
        sa.Column("rule_p90", sa.Integer),
        sa.Column("override_reason", sa.String(200)),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("live_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("live_count_at", sa.DateTime(timezone=True)),
        sa.Column("t90_status", sa.String(10), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("t90_live_count", sa.Integer),
        sa.Column("t90_projected", sa.Integer),
        sa.Column("t90_expected_surplus_g", sa.Integer),
        sa.Column("t90_reason", sa.String(200)),
        sa.Column("t90_decided_at", sa.DateTime(timezone=True)),
        sa.Column("t90_decided_by", sa.BigInteger, sa.ForeignKey("app_user.id")),
        sa.Column("actual_diners", sa.Integer),
        sa.Column("ran_short", sa.Boolean),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("kitchen_id", "meal_slot_id", "meal_date", name="uq_meal_kitchen_slot_date"),
        sa.CheckConstraint("status in ('PLANNED', 'ISSUED', 'IN_SERVICE', 'CLOSED')", name="ck_meal_status"),
        sa.CheckConstraint("forecast_method in ('RULE_V1', 'MANUAL')", name="ck_meal_forecast_method"),
        sa.CheckConstraint("t90_status in ('PENDING', 'CONFIRMED', 'CANCELLED', 'SKIPPED')",
                           name="ck_meal_t90_status"),
    )
    op.execute("alter table meal add constraint ck_meal_end_after_start"
               " check (service_end_at > service_start_at)")
    op.execute("alter table meal add constraint ck_meal_counts"
               " check (registered_count >= 0 and extra_opt_outs >= 0 and live_count >= 0)")
    op.execute("alter table meal add constraint ck_meal_p90_ge_p50"
               " check (p50 is null or p90 is null or p90 >= p50)")
    op.execute("alter table meal add constraint ck_meal_manual_reason"
               " check (forecast_method <> 'MANUAL' or override_reason is not null)")
    op.execute("alter table meal add constraint ck_meal_closed_has_actual"
               " check (status <> 'CLOSED' or actual_diners is not null)")

    op.create_table(
        "meal_dish",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("meal_id", sa.BigInteger, sa.ForeignKey("meal.id"), nullable=False),
        sa.Column("dish_id", sa.BigInteger, sa.ForeignKey("dish.id"), nullable=False),
        sa.Column("is_reserve", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("cooked_g_per_diner", sa.Integer, nullable=False),
        sa.Column("raw_g_per_diner", sa.Integer),
        sa.Column("line_g", sa.Integer),
        sa.Column("reserve_g", sa.Integer),
        sa.Column("usual_g", sa.Integer),
        sa.UniqueConstraint("meal_id", "dish_id", name="uq_meal_dish_meal_dish"),
        sa.CheckConstraint("cooked_g_per_diner > 0", name="ck_meal_dish_cooked_g"),
        sa.CheckConstraint("raw_g_per_diner is null or raw_g_per_diner > 0", name="ck_meal_dish_raw_g"),
    )
    op.execute("alter table meal_dish add constraint ck_meal_dish_amounts"
               " check ((line_g is null or line_g >= 0) and (reserve_g is null or reserve_g >= 0)"
               " and (usual_g is null or usual_g >= 0))")
    # exactly one reserve dish (= one lidded vessel) per meal
    op.execute("create unique index ux_meal_one_reserve on meal_dish(meal_id) where is_reserve")

    op.create_table(
        "opt_out",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("kitchen_id", sa.BigInteger, sa.ForeignKey("kitchen.id"), nullable=False),
        sa.Column("slot", sa.String(10), nullable=False),
        sa.Column("meal_date", sa.Date, nullable=False),
        sa.Column("hostel_id", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("kitchen_id", "slot", "meal_date", "hostel_id",
                            name="uq_opt_out_kitchen_slot_date_hostel"),
        sa.CheckConstraint(f"slot in {SLOTS}", name="ck_opt_out_slot"),
    )


def downgrade() -> None:
    op.drop_table("opt_out")
    op.execute("drop index ux_meal_one_reserve")
    op.drop_table("meal_dish")
    op.drop_table("meal")
    op.drop_table("dish")
    op.drop_table("meal_slot")
