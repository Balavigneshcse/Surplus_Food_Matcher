"""Batch record (revision 0005): the FSSAI Schedule II record, a frozen snapshot made at handover.

Fields 1-9 are copied as text at handover and never updated; fields 10-12 are set once by the NGO.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (BigInteger, CheckConstraint, ForeignKey, Identity, Numeric, String, UniqueConstraint,
                        Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BatchRecord(Base):
    __tablename__ = "batch_record"
    __table_args__ = (
        UniqueConstraint("batch_id", name="uq_batch_record_batch"),
        UniqueConstraint("public_token", name="uq_batch_record_token"),
        CheckConstraint("qty_donated_g > 0", name="ck_batch_record_qty_donated"),
        CheckConstraint("temp_c between -10 and 120", name="ck_batch_record_temp_range"),
        CheckConstraint("safeclock_at_handover in ('GREEN', 'AMBER')", name="ck_batch_record_safeclock"),
        # GREEN food gets a refrigerate-by time; AMBER food is served at once and never re-chilled
        CheckConstraint("(safeclock_at_handover = 'GREEN') = (refrigerate_by is not null)",
                        name="ck_batch_record_refrigerate_by"),
        # fields 10-12 are entered together, once
        CheckConstraint("(qty_distributed_g is null and area_of_distribution is null and distributed_on is null"
                        " and distribution_entered_at is null)"
                        " or (qty_distributed_g is not null and area_of_distribution is not null"
                        " and distributed_on is not null and distribution_entered_at is not null)",
                        name="ck_batch_record_distribution_once"),
        CheckConstraint("qty_distributed_g is null or qty_distributed_g between 0 and qty_donated_g",
                        name="ck_batch_record_qty_distributed"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    batch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reserve_batch.id"))
    offer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("offer.id"))
    public_token: Mapped[uuid.UUID] = mapped_column(Uuid)  # the QR / record.html?t= token
    # (1) donor
    donor_name: Mapped[str] = mapped_column(String(100))
    donor_address: Mapped[str] = mapped_column(String(300))
    donor_fssai_no: Mapped[str] = mapped_column(String(14))
    # (2) distributor
    distributor_name: Mapped[str] = mapped_column(String(100))
    distributor_address: Mapped[str] = mapped_column(String(300))
    distributor_fssai_no: Mapped[str] = mapped_column(String(14))
    # (3) date of donation
    donated_at: Mapped[datetime]
    # (4) name of food
    food_name: Mapped[str] = mapped_column(String(100))
    food_name_ta: Mapped[str | None] = mapped_column(String(100))
    # (5) batch number
    batch_no: Mapped[str] = mapped_column(String(30))
    # (6) date of manufacture
    manufactured_at: Mapped[datetime]
    # (7) best before: latest serving time; refrigerate_by is null if AMBER
    consume_by: Mapped[datetime]
    refrigerate_by: Mapped[datetime | None]
    # (8) quantity donated
    qty_donated_g: Mapped[int]
    # (9) temperature at handover
    temp_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    # extras shown on the record
    is_veg: Mapped[bool]
    pickup_at: Mapped[datetime]
    safeclock_at_handover: Mapped[str] = mapped_column(String(5))
    advance_notice_at: Mapped[datetime]
    mou_ref: Mapped[str] = mapped_column(String(50))
    trained_handler_confirmed: Mapped[bool]
    # (10)-(12) entered once by the NGO
    qty_distributed_g: Mapped[int | None]
    area_of_distribution: Mapped[str | None] = mapped_column(String(200))
    distributed_on: Mapped[date | None]
    distribution_entered_at: Mapped[datetime | None]
    distribution_entered_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
