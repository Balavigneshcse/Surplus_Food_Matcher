"""Planning tables (revision 0002): MealSlot, Dish, Meal, MealDish, OptOut."""
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (BigInteger, CheckConstraint, ForeignKey, Identity, Index, Numeric, String,
                        UniqueConstraint, false, func, text, true)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class MealSlot(Base):
    """Daily defaults for one slot of one kitchen (times, ratio, partner NGO, ...)."""
    __tablename__ = "meal_slot"
    __table_args__ = (
        UniqueConstraint("kitchen_id", "slot", name="uq_meal_slot_kitchen_slot"),
        CheckConstraint("slot in ('BREAKFAST', 'LUNCH', 'DINNER')", name="ck_meal_slot_slot"),
        CheckConstraint("service_end > service_start", name="ck_meal_slot_end_after_start"),
        CheckConstraint("attendance_ratio between 0 and 1", name="ck_meal_slot_ratio"),
        CheckConstraint("share_arrived_by_t90 > 0 and share_arrived_by_t90 <= 1", name="ck_meal_slot_share_t90"),
        CheckConstraint("buffer_pct >= 0", name="ck_meal_slot_buffer"),
        CheckConstraint("optout_cutoff_min >= 0", name="ck_meal_slot_cutoff"),
        CheckConstraint("pickup_offset_min >= 0", name="ck_meal_slot_pickup_offset"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kitchen_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("kitchen.id"))
    slot: Mapped[str] = mapped_column(String(10))
    service_start: Mapped[time]
    service_end: Mapped[time]
    optout_cutoff_min: Mapped[int] = mapped_column(server_default=text("180"))
    attendance_ratio: Mapped[Decimal] = mapped_column(Numeric(4, 3), server_default=text("0.850"))
    buffer_pct: Mapped[Decimal] = mapped_column(Numeric(4, 1), server_default=text("6.0"))
    share_arrived_by_t90: Mapped[Decimal] = mapped_column(Numeric(4, 3), server_default=text("0.400"))
    standing_ngo_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ngo.id"))
    pickup_offset_min: Mapped[int] = mapped_column(server_default=text("15"))
    rescue_enabled: Mapped[bool] = mapped_column(server_default=true())  # dinner: false


class Dish(Base):
    __tablename__ = "dish"
    __table_args__ = (
        UniqueConstraint("kitchen_id", "name", name="uq_dish_kitchen_name"),
        CheckConstraint("cooked_g_per_diner > 0", name="ck_dish_cooked_g"),
        CheckConstraint("raw_g_per_diner is null or raw_g_per_diner > 0", name="ck_dish_raw_g"),
        CheckConstraint("cost_per_kg_inr is null or cost_per_kg_inr >= 0", name="ck_dish_cost"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kitchen_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("kitchen.id"))
    name: Mapped[str] = mapped_column(String(100))
    name_ta: Mapped[str | None] = mapped_column(String(100))
    is_veg: Mapped[bool] = mapped_column(server_default=true())
    cooked_g_per_diner: Mapped[int]
    raw_g_per_diner: Mapped[int | None]
    cost_per_kg_inr: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    active: Mapped[bool] = mapped_column(server_default=true())


class Meal(Base):
    __tablename__ = "meal"
    __table_args__ = (
        UniqueConstraint("kitchen_id", "meal_slot_id", "meal_date", name="uq_meal_kitchen_slot_date"),
        CheckConstraint("status in ('PLANNED', 'ISSUED', 'IN_SERVICE', 'CLOSED')", name="ck_meal_status"),
        CheckConstraint("forecast_method in ('RULE_V1', 'MANUAL')", name="ck_meal_forecast_method"),
        CheckConstraint("t90_status in ('PENDING', 'CONFIRMED', 'CANCELLED', 'SKIPPED')", name="ck_meal_t90_status"),
        CheckConstraint("service_end_at > service_start_at", name="ck_meal_end_after_start"),
        CheckConstraint("registered_count >= 0 and extra_opt_outs >= 0 and live_count >= 0", name="ck_meal_counts"),
        CheckConstraint("p50 is null or p90 is null or p90 >= p50", name="ck_meal_p90_ge_p50"),
        CheckConstraint("forecast_method <> 'MANUAL' or override_reason is not null", name="ck_meal_manual_reason"),
        CheckConstraint("status <> 'CLOSED' or actual_diners is not null", name="ck_meal_closed_has_actual"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kitchen_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("kitchen.id"))
    meal_slot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("meal_slot.id"))
    meal_date: Mapped[date]
    service_start_at: Mapped[datetime]
    service_end_at: Mapped[datetime]  # = T in the T-90 rule
    status: Mapped[str] = mapped_column(String(12), server_default=text("'PLANNED'"))
    registered_count: Mapped[int]
    extra_opt_outs: Mapped[int] = mapped_column(server_default=text("0"))
    opted_out_count: Mapped[int | None]  # snapshot at issue
    attendance_ratio: Mapped[Decimal] = mapped_column(Numeric(4, 3))  # snapshot of the slot value
    buffer_pct: Mapped[Decimal] = mapped_column(Numeric(4, 1))  # snapshot of the slot value
    p50: Mapped[int | None]
    p90: Mapped[int | None]
    forecast_method: Mapped[str] = mapped_column(String(10), server_default=text("'RULE_V1'"))
    rule_p50: Mapped[int | None]
    rule_p90: Mapped[int | None]
    override_reason: Mapped[str | None] = mapped_column(String(200))
    issued_at: Mapped[datetime | None]
    live_count: Mapped[int] = mapped_column(server_default=text("0"))
    live_count_at: Mapped[datetime | None]
    t90_status: Mapped[str] = mapped_column(String(10), server_default=text("'PENDING'"))
    t90_live_count: Mapped[int | None]
    t90_projected: Mapped[int | None]
    t90_expected_surplus_g: Mapped[int | None]
    t90_reason: Mapped[str | None] = mapped_column(String(200))
    t90_decided_at: Mapped[datetime | None]
    t90_decided_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))  # null = system
    actual_diners: Mapped[int | None]
    ran_short: Mapped[bool | None]
    closed_at: Mapped[datetime | None]
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    version: Mapped[int] = mapped_column(server_default=text("1"))

    slot: Mapped["MealSlot"] = relationship()
    dishes: Mapped[list["MealDish"]] = relationship(back_populates="meal", order_by="MealDish.id")

    # UPDATE ... WHERE version = ?; 0 rows -> StaleDataError -> 409 CONCURRENT_EDIT
    __mapper_args__ = {"version_id_col": version}


class MealDish(Base):
    """One dish on one meal's menu. g/diner values are copied from the dish so history never changes."""
    __tablename__ = "meal_dish"
    __table_args__ = (
        UniqueConstraint("meal_id", "dish_id", name="uq_meal_dish_meal_dish"),
        # exactly one reserve dish (= one lidded vessel) per meal
        Index("ux_meal_one_reserve", "meal_id", unique=True, postgresql_where=text("is_reserve")),
        CheckConstraint("cooked_g_per_diner > 0", name="ck_meal_dish_cooked_g"),
        CheckConstraint("raw_g_per_diner is null or raw_g_per_diner > 0", name="ck_meal_dish_raw_g"),
        CheckConstraint("(line_g is null or line_g >= 0) and (reserve_g is null or reserve_g >= 0)"
                        " and (usual_g is null or usual_g >= 0)", name="ck_meal_dish_amounts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    meal_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("meal.id"))
    dish_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dish.id"))
    is_reserve: Mapped[bool] = mapped_column(server_default=false())
    cooked_g_per_diner: Mapped[int]
    raw_g_per_diner: Mapped[int | None]
    line_g: Mapped[int | None]
    reserve_g: Mapped[int | None]
    usual_g: Mapped[int | None]  # the "usual" amount, in the same unit the card shows

    meal: Mapped["Meal"] = relationship(back_populates="dishes")
    dish: Mapped["Dish"] = relationship()


class OptOut(Base):
    """A student's opt-out, stored by slot + date (hostel ID only). Deleted 30 days after the meal closes."""
    __tablename__ = "opt_out"
    __table_args__ = (
        UniqueConstraint("kitchen_id", "slot", "meal_date", "hostel_id", name="uq_opt_out_kitchen_slot_date_hostel"),
        CheckConstraint("slot in ('BREAKFAST', 'LUNCH', 'DINNER')", name="ck_opt_out_slot"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kitchen_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("kitchen.id"))
    slot: Mapped[str] = mapped_column(String(10))
    meal_date: Mapped[date]
    hostel_id: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
