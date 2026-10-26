"""route log: where leftovers went, with the waste hierarchy enforced by the database

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "route_log",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("kitchen_id", sa.BigInteger, sa.ForeignKey("kitchen.id"), nullable=False),
        sa.Column("meal_id", sa.BigInteger, sa.ForeignKey("meal.id")),
        sa.Column("batch_id", sa.BigInteger, sa.ForeignKey("reserve_batch.id")),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("destination", sa.String(12), nullable=False),
        sa.Column("qty_g", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(200)),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("logged_by", sa.BigInteger, sa.ForeignKey("app_user.id"), nullable=False),
        sa.CheckConstraint("category in ('RESERVE_DONATED', 'RESERVE_UNCLAIMED', 'RESERVE_UNSAFE',"
                           " 'COOKED_UNSERVED', 'PLATE_WASTE', 'RAW_VEG_TRIMMINGS')", name="ck_route_log_category"),
        sa.CheckConstraint("destination in ('NGO', 'CATTLE_FEED', 'BIOGAS', 'COMPOST', 'LANDFILL')",
                           name="ck_route_log_destination"),
        sa.CheckConstraint("qty_g > 0", name="ck_route_log_qty"),
    )
    op.create_index("ix_route_log_kitchen_logged_at", "route_log", ["kitchen_id", "logged_at"])
    # waste hierarchy enforced by the database (a % inside op.execute is escaped for psycopg)
    op.execute("""alter table route_log
      add constraint ck_cattle_raw_veg_only check (destination <> 'CATTLE_FEED' or category = 'RAW_VEG_TRIMMINGS'),
      add constraint ck_ngo_only_donated    check ((destination = 'NGO') = (category = 'RESERVE_DONATED')),
      add constraint ck_reserve_has_batch   check (category not like 'RESERVE%' or batch_id is not null),
      add constraint ck_landfill_reason     check (destination <> 'LANDFILL' or reason is not null)""")


def downgrade() -> None:
    op.drop_index("ix_route_log_kitchen_logged_at", table_name="route_log")
    op.drop_table("route_log")
