"""SafeClock tables (revision 0003): ReserveBatch (the one lidded vessel) and ProbeReading."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (BigInteger, CheckConstraint, ForeignKey, Identity, Index, Numeric, String, Text,
                        UniqueConstraint, func, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ReserveBatch(Base):
    __tablename__ = "reserve_batch"
    __table_args__ = (
        UniqueConstraint("meal_id", name="uq_reserve_batch_meal"),  # one vessel per meal
        UniqueConstraint("batch_no", name="uq_reserve_batch_batch_no"),
        CheckConstraint("status in ('HOLDING', 'OFFERED', 'ACCEPTED', 'HANDED_OVER', 'USED_FOR_STUDENTS',"
                        " 'TO_DISPOSE', 'ROUTED')", name="ck_reserve_batch_status"),
        CheckConstraint("worst_colour in ('GREEN', 'AMBER', 'RED')", name="ck_reserve_batch_worst_colour"),
        CheckConstraint("planned_g >= 0", name="ck_reserve_batch_planned_g"),
        CheckConstraint("lidded_weight_g is null or lidded_weight_g > 0", name="ck_reserve_batch_lidded_weight"),
        CheckConstraint("prepared_at <= lidded_at", name="ck_reserve_batch_prepared_before_lid"),
        CheckConstraint("status not in ('ACCEPTED', 'HANDED_OVER') or accepted_ngo_id is not null",
                        name="ck_reserve_batch_accepted_has_ngo"),
        CheckConstraint("status <> 'TO_DISPOSE' or dispose_reason is not null",
                        name="ck_reserve_batch_dispose_reason"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    meal_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("meal.id"))
    meal_dish_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("meal_dish.id"))
    batch_no: Mapped[str] = mapped_column(String(30))  # e.g. MESS1-20261030-L
    food_name: Mapped[str] = mapped_column(String(100))
    is_veg: Mapped[bool]
    planned_g: Mapped[int]
    lidded_weight_g: Mapped[int | None]
    prepared_at: Mapped[datetime]
    lidded_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(20), server_default=text("'HOLDING'"))
    worst_colour: Mapped[str] = mapped_column(String(5), server_default=text("'GREEN'"))
    accepted_ngo_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ngo.id"))
    pickup_at: Mapped[datetime | None]
    dispose_reason: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    version: Mapped[int] = mapped_column(server_default=text("1"))  # must be assigned, or __mapper_args__ can't name it

    # Read-only view of the log: readings are only ever inserted (the table is append-only).
    readings: Mapped[list["ProbeReading"]] = relationship(viewonly=True, order_by="ProbeReading.read_at")

    # UPDATE ... WHERE version = ?; 0 rows -> StaleDataError -> 409
    __mapper_args__ = {"version_id_col": version}


class ProbeReading(Base):
    """The probe log is evidence: no edits, no deletes (a database trigger enforces it).
    A correction is a new reading with a note."""
    __tablename__ = "probe_reading"
    __table_args__ = (
        CheckConstraint("temp_c between -10 and 120", name="ck_probe_temp_range"),
        CheckConstraint("kind in ('LID', 'ROUTINE', 'HANDOVER')", name="ck_probe_kind"),
        Index("ix_probe_batch_read_at", "batch_id", "read_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    batch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reserve_batch.id"))
    temp_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    read_at: Mapped[datetime]  # from the app clock, never the database's now()
    kind: Mapped[str] = mapped_column(String(10))
    recorded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    note: Mapped[str | None] = mapped_column(Text)
