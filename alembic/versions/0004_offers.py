"""offers: offer (partner seq 0, overflow seq 1-3)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("batch_id", sa.BigInteger, sa.ForeignKey("reserve_batch.id"), nullable=False),
        sa.Column("ngo_id", sa.BigInteger, sa.ForeignKey("ngo.id"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(10), nullable=False, server_default=sa.text("'IN_APP'")),
        sa.Column("status", sa.String(10), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("qty_g", sa.Integer, nullable=False),
        sa.Column("pickup_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("responded_by", sa.BigInteger, sa.ForeignKey("app_user.id")),
        sa.Column("reason", sa.String(200)),
        sa.UniqueConstraint("batch_id", "seq", name="uq_offer_batch_seq"),
        sa.UniqueConstraint("batch_id", "ngo_id", name="uq_offer_batch_ngo"),
        sa.CheckConstraint("seq between 0 and 3", name="ck_offer_seq"),
        sa.CheckConstraint("channel in ('IN_APP')", name="ck_offer_channel"),
        sa.CheckConstraint("status in ('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'WITHDRAWN', 'COLLECTED',"
                           " 'NO_SHOW')", name="ck_offer_status"),
        sa.CheckConstraint("qty_g > 0", name="ck_offer_qty"),
    )
    op.execute("alter table offer add constraint ck_offer_expires_after_sent check (expires_at > sent_at)")
    op.create_index("ix_offer_status_expires", "offer", ["status", "expires_at"])
    # one live offer at a time; the first Accept locks the batch (database backstop)
    op.execute("create unique index ux_offer_one_pending on offer(batch_id) where status = 'PENDING'")
    op.execute("create unique index ux_offer_one_taker on offer(batch_id)"
               " where status in ('ACCEPTED', 'COLLECTED', 'NO_SHOW')")


def downgrade() -> None:
    op.execute("drop index ux_offer_one_taker")
    op.execute("drop index ux_offer_one_pending")
    op.drop_index("ix_offer_status_expires", table_name="offer")
    op.drop_table("offer")
