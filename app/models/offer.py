"""Offers (revision 0004): seq 0 = standing partner, 1-3 = overflow offers."""
from datetime import datetime

from sqlalchemy import (BigInteger, CheckConstraint, ForeignKey, Identity, Index, String, UniqueConstraint,
                        text)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Offer(Base):
    __tablename__ = "offer"
    __table_args__ = (
        UniqueConstraint("batch_id", "seq", name="uq_offer_batch_seq"),
        UniqueConstraint("batch_id", "ngo_id", name="uq_offer_batch_ngo"),
        # one live offer at a time; the first Accept locks the batch (database backstop)
        Index("ux_offer_one_pending", "batch_id", unique=True, postgresql_where=text("status = 'PENDING'")),
        Index("ux_offer_one_taker", "batch_id", unique=True,
              postgresql_where=text("status in ('ACCEPTED', 'COLLECTED', 'NO_SHOW')")),
        Index("ix_offer_status_expires", "status", "expires_at"),
        CheckConstraint("seq between 0 and 3", name="ck_offer_seq"),
        CheckConstraint("channel in ('IN_APP')", name="ck_offer_channel"),
        CheckConstraint("status in ('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'WITHDRAWN', 'COLLECTED',"
                        " 'NO_SHOW')", name="ck_offer_status"),
        CheckConstraint("qty_g > 0", name="ck_offer_qty"),
        CheckConstraint("expires_at > sent_at", name="ck_offer_expires_after_sent"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    batch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reserve_batch.id"))
    ngo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ngo.id"))
    seq: Mapped[int]
    channel: Mapped[str] = mapped_column(String(10), server_default=text("'IN_APP'"))
    status: Mapped[str] = mapped_column(String(10), server_default=text("'PENDING'"))
    qty_g: Mapped[int]
    pickup_at: Mapped[datetime]
    sent_at: Mapped[datetime]  # the FSSAI "advance notice" time shown on the record
    expires_at: Mapped[datetime]
    responded_at: Mapped[datetime | None]
    responded_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    reason: Mapped[str | None] = mapped_column(String(200))
