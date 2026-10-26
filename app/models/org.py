"""Organisations and users (revision 0001): Kitchen, Ngo, Partnership, AppUser.

Models mirror the Alembic migrations; they never create tables themselves.
"""
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (BigInteger, CheckConstraint, ForeignKey, Identity, Numeric, String,
                        UniqueConstraint, false, func, text, true)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Kitchen(Base):
    __tablename__ = "kitchen"
    __table_args__ = (
        UniqueConstraint("code", name="uq_kitchen_code"),
        CheckConstraint("fssai_licence_no ~ '^[0-9]{14}$'", name="ck_kitchen_fssai_licence"),
        CheckConstraint("side_dish_basis in ('P50_TOPUP', 'P90')", name="ck_kitchen_side_dish_basis"),
        CheckConstraint("registered_diners >= 0", name="ck_kitchen_registered_diners"),
        CheckConstraint("default_min_batch_g > 0", name="ck_kitchen_min_batch"),
        CheckConstraint("max_radius_km > 0", name="ck_kitchen_radius"),
        CheckConstraint("g_per_meal_equiv > 0", name="ck_kitchen_meal_equiv"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(20))  # used in the opt-out link, e.g. MESS1
    name: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(300))
    fssai_licence_no: Mapped[str] = mapped_column(String(14))
    registered_diners: Mapped[int]
    default_min_batch_g: Mapped[int] = mapped_column(server_default=text("8000"))
    max_radius_km: Mapped[Decimal] = mapped_column(Numeric(5, 1), server_default=text("15.0"))
    side_dish_basis: Mapped[str] = mapped_column(String(10), server_default=text("'P50_TOPUP'"))
    g_per_meal_equiv: Mapped[int] = mapped_column(server_default=text("420"))
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Ngo(Base):
    __tablename__ = "ngo"
    __table_args__ = (
        CheckConstraint("fssai_reg_no ~ '^[0-9]{14}$'", name="ck_ngo_fssai_reg_no"),
        CheckConstraint("capacity_g > 0", name="ck_ngo_capacity"),
        CheckConstraint("min_batch_g > 0", name="ck_ngo_min_batch"),
        CheckConstraint("open_to > open_from", name="ck_ngo_open_hours"),
        CheckConstraint("contact_phone is null or phone_consent_at is not null", name="ck_ngo_phone_consent"),
        CheckConstraint("pickups_on_time between 0 and pickups_total", name="ck_ngo_pickups"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(300))
    fssai_reg_no: Mapped[str] = mapped_column(String(14))
    fssai_verified_at: Mapped[datetime | None]  # null = never offered (admin has not checked it)
    fssai_valid_until: Mapped[date | None]
    accepts_veg: Mapped[bool] = mapped_column(server_default=true())
    accepts_nonveg: Mapped[bool] = mapped_column(server_default=false())
    capacity_g: Mapped[int]
    min_batch_g: Mapped[int] = mapped_column(server_default=text("8000"))
    has_reheating: Mapped[bool] = mapped_column(server_default=false())
    has_trained_handler: Mapped[bool] = mapped_column(server_default=false())
    open_from: Mapped[time]
    open_to: Mapped[time]
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    contact_phone: Mapped[str | None] = mapped_column(String(15))
    phone_consent_at: Mapped[datetime | None]
    pickups_total: Mapped[int] = mapped_column(server_default=text("0"))
    pickups_on_time: Mapped[int] = mapped_column(server_default=text("0"))
    active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Partnership(Base):
    """The MoU between one kitchen and one NGO. No active MoU = never offered."""
    __tablename__ = "partnership"
    __table_args__ = (UniqueConstraint("kitchen_id", "ngo_id", name="uq_partnership_kitchen_ngo"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kitchen_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("kitchen.id"))
    ngo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ngo.id"))
    mou_ref: Mapped[str] = mapped_column(String(50))
    mou_valid_until: Mapped[date | None]  # null = no end date
    active: Mapped[bool] = mapped_column(server_default=true())


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = (
        UniqueConstraint("username", name="uq_app_user_username"),
        CheckConstraint("role in ('ADMIN', 'KITCHEN', 'NGO')", name="ck_app_user_role"),
        CheckConstraint("role <> 'KITCHEN' or kitchen_id is not null", name="ck_app_user_kitchen_role"),
        CheckConstraint("role <> 'NGO' or ngo_id is not null", name="ck_app_user_ngo_role"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    username: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(10))
    kitchen_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("kitchen.id"))
    ngo_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ngo.id"))
    enabled: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
