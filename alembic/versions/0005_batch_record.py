"""batch record: the frozen Schedule II record made at handover

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batch_record",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("batch_id", sa.BigInteger, sa.ForeignKey("reserve_batch.id"), nullable=False),
        sa.Column("offer_id", sa.BigInteger, sa.ForeignKey("offer.id"), nullable=False),
        sa.Column("public_token", sa.Uuid, nullable=False),
        # (1) donor
        sa.Column("donor_name", sa.String(100), nullable=False),
        sa.Column("donor_address", sa.String(300), nullable=False),
        sa.Column("donor_fssai_no", sa.String(14), nullable=False),
        # (2) distributor
        sa.Column("distributor_name", sa.String(100), nullable=False),
        sa.Column("distributor_address", sa.String(300), nullable=False),
        sa.Column("distributor_fssai_no", sa.String(14), nullable=False),
        # (3) date of donation
        sa.Column("donated_at", sa.DateTime(timezone=True), nullable=False),
        # (4) name of food
        sa.Column("food_name", sa.String(100), nullable=False),
        sa.Column("food_name_ta", sa.String(100)),
        # (5) batch number
        sa.Column("batch_no", sa.String(30), nullable=False),
        # (6) date of manufacture
        sa.Column("manufactured_at", sa.DateTime(timezone=True), nullable=False),
        # (7) best before (latest serving time); refrigerate_by is null if AMBER
        sa.Column("consume_by", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refrigerate_by", sa.DateTime(timezone=True)),
        # (8) quantity donated
        sa.Column("qty_donated_g", sa.Integer, nullable=False),
        # (9) temperature at handover
        sa.Column("temp_c", sa.Numeric(4, 1), nullable=False),
        # extras
        sa.Column("is_veg", sa.Boolean, nullable=False),
        sa.Column("pickup_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("safeclock_at_handover", sa.String(5), nullable=False),
        sa.Column("advance_notice_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mou_ref", sa.String(50), nullable=False),
        sa.Column("trained_handler_confirmed", sa.Boolean, nullable=False),
        # (10)-(12) entered once by the NGO
        sa.Column("qty_distributed_g", sa.Integer),
        sa.Column("area_of_distribution", sa.String(200)),
        sa.Column("distributed_on", sa.Date),
        sa.Column("distribution_entered_at", sa.DateTime(timezone=True)),
        sa.Column("distribution_entered_by", sa.BigInteger, sa.ForeignKey("app_user.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("batch_id", name="uq_batch_record_batch"),
        sa.UniqueConstraint("public_token", name="uq_batch_record_token"),
        sa.CheckConstraint("qty_donated_g > 0", name="ck_batch_record_qty_donated"),
        sa.CheckConstraint("temp_c between -10 and 120", name="ck_batch_record_temp_range"),
        sa.CheckConstraint("safeclock_at_handover in ('GREEN', 'AMBER')", name="ck_batch_record_safeclock"),
    )
    # GREEN food gets a refrigerate-by time; AMBER food is served at once and never re-chilled
    op.execute("alter table batch_record add constraint ck_batch_record_refrigerate_by"
               " check ((safeclock_at_handover = 'GREEN') = (refrigerate_by is not null))")
    # fields 10-12 are entered together, once
    op.execute("alter table batch_record add constraint ck_batch_record_distribution_once check ("
               "(qty_distributed_g is null and area_of_distribution is null and distributed_on is null"
               " and distribution_entered_at is null)"
               " or (qty_distributed_g is not null and area_of_distribution is not null"
               " and distributed_on is not null and distribution_entered_at is not null))")
    op.execute("alter table batch_record add constraint ck_batch_record_qty_distributed"
               " check (qty_distributed_g is null or qty_distributed_g between 0 and qty_donated_g)")


def downgrade() -> None:
    op.drop_table("batch_record")
