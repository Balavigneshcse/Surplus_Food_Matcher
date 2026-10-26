"""Schemas for slots, dishes, meals (forecast + cook card) and opt-outs.

JSON is camelCase (ApiModel). Weights are integer grams; ratios and percentages are JSON numbers.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from pydantic import Field, PlainSerializer, field_validator, model_validator

from app.schemas.common import ApiModel, IstDateTime, Slot

# Pydantic writes Decimal as a JSON string by default; send these as numbers (like TempC).
Ratio = Annotated[Decimal, Field(ge=0, le=1, max_digits=4, decimal_places=3),
                  PlainSerializer(float, return_type=float, when_used="json")]
ShareT90 = Annotated[Decimal, Field(gt=0, le=1, max_digits=4, decimal_places=3),
                     PlainSerializer(float, return_type=float, when_used="json")]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=4, decimal_places=1),
                    PlainSerializer(float, return_type=float, when_used="json")]
Rupees = Annotated[Decimal, Field(ge=0, max_digits=8, decimal_places=2),
                   PlainSerializer(float, return_type=float, when_used="json")]

GramsPerDiner = Annotated[int, Field(gt=0, le=5000)]
Diners = Annotated[int, Field(ge=0, le=100000)]


def _strip(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value


# ---------------------------------------------------------------- kitchen setup: slots

class KitchenInfo(ApiModel):
    id: int
    code: str
    name: str
    registered_diners: int
    side_dish_basis: str  # P50_TOPUP (default) or P90; changed by the admin


class PartnerOption(ApiModel):
    """An NGO with an active MoU with this kitchen (can be a slot's standing partner)."""
    id: int
    name: str


class SlotOut(ApiModel):
    id: int
    slot: Slot
    service_start: dt.time
    service_end: dt.time
    optout_cutoff_min: int
    attendance_ratio: Ratio
    buffer_pct: Percent
    share_arrived_by_t90: ShareT90
    standing_ngo_id: int | None
    standing_ngo_name: str | None = None
    pickup_offset_min: int
    rescue_enabled: bool


class SlotListOut(ApiModel):
    kitchen: KitchenInfo
    slots: list[SlotOut]
    partners: list[PartnerOption]


class SlotIn(ApiModel):
    service_start: dt.time
    service_end: dt.time
    optout_cutoff_min: int = Field(ge=0, le=1440)
    attendance_ratio: Ratio
    buffer_pct: Percent
    share_arrived_by_t90: ShareT90
    standing_ngo_id: int | None = None
    pickup_offset_min: int = Field(ge=0, le=240)
    rescue_enabled: bool

    @model_validator(mode="after")
    def end_after_start(self) -> "SlotIn":
        if self.service_end <= self.service_start:
            raise ValueError("Service must end after it starts")
        return self


# ---------------------------------------------------------------- kitchen setup: dishes

class DishOut(ApiModel):
    id: int
    name: str
    name_ta: str | None
    is_veg: bool
    cooked_g_per_diner: int
    raw_g_per_diner: int | None
    cost_per_kg_inr: Rupees | None
    active: bool


class DishIn(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    name_ta: str | None = Field(default=None, max_length=100)
    is_veg: bool = True
    cooked_g_per_diner: GramsPerDiner
    raw_g_per_diner: GramsPerDiner | None = None
    cost_per_kg_inr: Rupees | None = None
    active: bool = True

    @field_validator("name", "name_ta", mode="before")
    @classmethod
    def strip_spaces(cls, value):
        return _strip(value)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("name_ta")
    @classmethod
    def empty_tamil_name_is_none(cls, value: str | None) -> str | None:
        return value or None


# ---------------------------------------------------------------- meals: requests

class MenuDishIn(ApiModel):
    dish_id: int
    is_reserve: bool = False
    usual_g: int | None = Field(default=None, ge=0, le=10_000_000)  # the "usual" cooked grams, for comparison


class MealCreateIn(ApiModel):
    slot_id: int
    date: dt.date
    registered_count: Diners | None = None  # default: the kitchen's registered diners
    extra_opt_outs: Diners = 0  # "opt-outs from another app"
    dishes: list[MenuDishIn] = Field(min_length=1, max_length=20)


class MealUpdateIn(ApiModel):
    registered_count: Diners
    extra_opt_outs: Diners = 0
    dishes: list[MenuDishIn] = Field(min_length=1, max_length=20)
    version: int | None = None  # the version the page loaded; a different one answers 409 CONCURRENT_EDIT


class OverrideIn(ApiModel):
    p50: Diners
    p90: Diners
    reason: str | None = Field(default=None, max_length=200)
    version: int | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def strip_spaces(cls, value):
        return _strip(value)


class LiveCountIn(ApiModel):
    """Send either `count` (set the door tally) or `delta` (+1, +10, or a negative correction)."""
    count: Diners | None = None
    delta: int | None = Field(default=None, ge=-1000, le=1000)

    @model_validator(mode="after")
    def exactly_one(self) -> "LiveCountIn":
        if (self.count is None) == (self.delta is None):
            raise ValueError("Send either count or delta")
        return self


# ---------------------------------------------------------------- meals: responses

class ForecastOut(ApiModel):
    p50: int
    p90: int
    method: str  # RULE_V1 / MANUAL
    rule_p50: int  # what the rule says (kept next to a manual forecast for comparison)
    rule_p90: int
    override_reason: str | None
    frozen: bool  # true once the cook card is issued


class CookCardLine(ApiModel):
    meal_dish_id: int
    dish_id: int
    name: str
    name_ta: str | None
    is_veg: bool
    is_reserve: bool
    cooked_g_per_diner: int
    raw_g_per_diner: int | None
    line_g: int  # serving line, cooked
    reserve_g: int  # RESERVE VESSEL, cooked (reserve dish only)
    top_up_g: int  # top-up ready (20-min quick cook), side dishes on the P50_TOPUP basis
    raw_g: int | None  # raw amount to cook (only when raw g/diner is set)
    raw_diners: int
    planned_g: int  # line + reserve: compared with the usual amount
    usual_g: int | None


class T90Out(ApiModel):
    status: str
    live_count: int | None
    projected: int | None
    expected_surplus_g: int | None
    reason: str | None
    decided_at: IstDateTime | None


class MealView(ApiModel):
    """Full meal view: forecast, cook card and T-90 numbers. (The reserve batch with SafeClock and the
    offer timeline join this view in their own phases.)"""
    id: int
    kitchen_code: str
    kitchen_name: str
    slot_id: int
    slot: Slot
    date: dt.date
    status: str
    service_start_at: IstDateTime
    service_end_at: IstDateTime
    cutoff_at: IstDateTime  # opt-outs close, and the card issues itself, at this time
    optout_open: bool
    registered_count: int
    opt_out_rows: int  # students who opted out on optout.html
    extra_opt_outs: int  # "opt-outs from another app"
    opted_out: int  # both together (frozen at issue)
    eligible: int
    attendance_ratio: Ratio
    buffer_pct: Percent
    side_dish_basis: str
    forecast: ForecastOut
    cook_card: list[CookCardLine]
    reserve_g: int  # the reserve vessel (cooked grams)
    issued_at: IstDateTime | None
    live_count: int
    live_count_at: IstDateTime | None
    t90: T90Out
    actual_diners: int | None
    ran_short: bool | None
    closed_at: IstDateTime | None
    version: int
    server_now: IstDateTime


class MealSummary(ApiModel):
    id: int
    slot_id: int
    slot: Slot
    date: dt.date
    status: str
    service_start_at: IstDateTime
    service_end_at: IstDateTime
    cutoff_at: IstDateTime
    registered_count: int
    opted_out: int
    p50: int
    p90: int
    method: str
    frozen: bool
    reserve_g: int
    live_count: int
    t90_status: str


class MealListOut(ApiModel):
    date: dt.date
    meals: list[MealSummary]
    server_now: IstDateTime


# ---------------------------------------------------------------- public: opt-outs

class OpenMeal(ApiModel):
    date: dt.date
    slot: Slot
    service_start_at: IstDateTime
    cutoff_at: IstDateTime


class OpenMealsOut(ApiModel):
    kitchen_code: str
    kitchen_name: str
    meals: list[OpenMeal]
    sample_data: bool  # true in demo mode: the page shows the SAMPLE DATA banner (students never log in)
    server_now: IstDateTime


class OptOutIn(ApiModel):
    """Sent in the body, never in the URL (the hostel ID is personal data)."""
    kitchen_code: str = Field(min_length=1, max_length=20)
    date: dt.date
    slot: Slot
    hostel_id: str = Field(min_length=1, max_length=40)

    @field_validator("kitchen_code", "hostel_id", mode="before")
    @classmethod
    def strip_spaces(cls, value):
        return _strip(value)


class OptOutResult(ApiModel):
    """The same answer whether or not this hostel ID had already opted out, so nobody can use the page to
    find out what another student did (anyone can type any hostel ID)."""
    kitchen_code: str
    date: dt.date
    slot: Slot
    opted_out: bool  # the state after this request
    cutoff_at: IstDateTime
    server_now: IstDateTime
