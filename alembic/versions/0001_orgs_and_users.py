"""orgs and users: kitchen, ngo, partnership, app_user

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kitchen",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("fssai_licence_no", sa.String(14), nullable=False),
        sa.Column("registered_diners", sa.Integer, nullable=False),
        sa.Column("default_min_batch_g", sa.Integer, nullable=False, server_default=sa.text("8000")),
        sa.Column("max_radius_km", sa.Numeric(5, 1), nullable=False, server_default=sa.text("15.0")),
        sa.Column("side_dish_basis", sa.String(10), nullable=False, server_default=sa.text("'P50_TOPUP'")),
        sa.Column("g_per_meal_equiv", sa.Integer, nullable=False, server_default=sa.text("420")),
        sa.Column("lat", sa.Numeric(9, 6)),
        sa.Column("lng", sa.Numeric(9, 6)),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_kitchen_code"),
        sa.CheckConstraint("fssai_licence_no ~ '^[0-9]{14}$'", name="ck_kitchen_fssai_licence"),
        sa.CheckConstraint("side_dish_basis in ('P50_TOPUP', 'P90')", name="ck_kitchen_side_dish_basis"),
        sa.CheckConstraint("registered_diners >= 0", name="ck_kitchen_registered_diners"),
        sa.CheckConstraint("default_min_batch_g > 0", name="ck_kitchen_min_batch"),
        sa.CheckConstraint("max_radius_km > 0", name="ck_kitchen_radius"),
        sa.CheckConstraint("g_per_meal_equiv > 0", name="ck_kitchen_meal_equiv"),
    )

    op.create_table(
        "ngo",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("fssai_reg_no", sa.String(14), nullable=False),
        sa.Column("fssai_verified_at", sa.DateTime(timezone=True)),
        sa.Column("fssai_valid_until", sa.Date),
        sa.Column("accepts_veg", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("accepts_nonveg", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("capacity_g", sa.Integer, nullable=False),
        sa.Column("min_batch_g", sa.Integer, nullable=False, server_default=sa.text("8000")),
        sa.Column("has_reheating", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("has_trained_handler", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("open_from", sa.Time, nullable=False),
        sa.Column("open_to", sa.Time, nullable=False),
        sa.Column("lat", sa.Numeric(9, 6)),
        sa.Column("lng", sa.Numeric(9, 6)),
        sa.Column("contact_phone", sa.String(15)),
        sa.Column("phone_consent_at", sa.DateTime(timezone=True)),
        sa.Column("pickups_total", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("pickups_on_time", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("fssai_reg_no ~ '^[0-9]{14}$'", name="ck_ngo_fssai_reg_no"),
        sa.CheckConstraint("capacity_g > 0", name="ck_ngo_capacity"),
        sa.CheckConstraint("min_batch_g > 0", name="ck_ngo_min_batch"),
    )
    # multi-column rules
    op.execute("alter table ngo add constraint ck_ngo_open_hours check (open_to > open_from)")
    op.execute("alter table ngo add constraint ck_ngo_phone_consent"
               " check (contact_phone is null or phone_consent_at is not null)")
    op.execute("alter table ngo add constraint ck_ngo_pickups check (pickups_on_time between 0 and pickups_total)")

    op.create_table(
        "partnership",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("kitchen_id", sa.BigInteger, sa.ForeignKey("kitchen.id"), nullable=False),
        sa.Column("ngo_id", sa.BigInteger, sa.ForeignKey("ngo.id"), nullable=False),
        sa.Column("mou_ref", sa.String(50), nullable=False),
        sa.Column("mou_valid_until", sa.Date),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("kitchen_id", "ngo_id", name="uq_partnership_kitchen_ngo"),
    )

    op.create_table(
        "app_user",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("kitchen_id", sa.BigInteger, sa.ForeignKey("kitchen.id")),
        sa.Column("ngo_id", sa.BigInteger, sa.ForeignKey("ngo.id")),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("username", name="uq_app_user_username"),
        # to split roles later, edit this one CHECK (and the router role rules)
        sa.CheckConstraint("role in ('ADMIN', 'KITCHEN', 'NGO')", name="ck_app_user_role"),
    )
    op.execute("alter table app_user add constraint ck_app_user_kitchen_role"
               " check (role <> 'KITCHEN' or kitchen_id is not null)")
    op.execute("alter table app_user add constraint ck_app_user_ngo_role"
               " check (role <> 'NGO' or ngo_id is not null)")


def downgrade() -> None:
    op.drop_table("app_user")
    op.drop_table("partnership")
    op.drop_table("ngo")
    op.drop_table("kitchen")
