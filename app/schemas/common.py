"""Shared schema pieces: the camelCase base model, IST datetimes, temperatures and the enums.

Python code uses snake_case; JSON uses camelCase through ApiModel's alias generator.
"""
import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel

from app.core.clock import IST


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True,
                              serialize_by_alias=True, from_attributes=True)


def _assume_ist(d: dt.datetime) -> dt.datetime:
    """Input with no offset means IST."""
    return d.replace(tzinfo=IST) if d.tzinfo is None else d


# Pydantic writes Decimal as a JSON string by default; send temperatures as numbers instead.
TempC = Annotated[Decimal, Field(ge=-10, le=120, max_digits=4, decimal_places=1),
                  PlainSerializer(float, return_type=float, when_used="json")]

# Every datetime in a schema uses this: stored as UTC, shown with the IST offset (+05:30).
IstDateTime = Annotated[dt.datetime, AfterValidator(_assume_ist),
                        PlainSerializer(lambda d: d.astimezone(IST).isoformat(),
                                        return_type=str, when_used="json")]


# ---- Enums: a StrEnum member equals its string, so comparisons with DB values just work ----

class Role(StrEnum):
    ADMIN = "ADMIN"
    KITCHEN = "KITCHEN"
    NGO = "NGO"


class Slot(StrEnum):
    BREAKFAST = "BREAKFAST"
    LUNCH = "LUNCH"
    DINNER = "DINNER"


class SideDishBasis(StrEnum):
    P50_TOPUP = "P50_TOPUP"
    P90 = "P90"


class MealStatus(StrEnum):
    PLANNED = "PLANNED"
    ISSUED = "ISSUED"
    IN_SERVICE = "IN_SERVICE"
    CLOSED = "CLOSED"


class ForecastMethod(StrEnum):
    RULE_V1 = "RULE_V1"
    MANUAL = "MANUAL"


class T90Status(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class BatchStatus(StrEnum):
    HOLDING = "HOLDING"
    OFFERED = "OFFERED"
    ACCEPTED = "ACCEPTED"
    HANDED_OVER = "HANDED_OVER"
    USED_FOR_STUDENTS = "USED_FOR_STUDENTS"
    TO_DISPOSE = "TO_DISPOSE"
    ROUTED = "ROUTED"


class Colour(StrEnum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class ProbeKind(StrEnum):
    LID = "LID"
    ROUTINE = "ROUTINE"
    HANDOVER = "HANDOVER"


class OfferChannel(StrEnum):
    IN_APP = "IN_APP"


class OfferStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"
    COLLECTED = "COLLECTED"
    NO_SHOW = "NO_SHOW"


class RouteCategory(StrEnum):
    RESERVE_DONATED = "RESERVE_DONATED"
    RESERVE_UNCLAIMED = "RESERVE_UNCLAIMED"
    RESERVE_UNSAFE = "RESERVE_UNSAFE"
    COOKED_UNSERVED = "COOKED_UNSERVED"
    PLATE_WASTE = "PLATE_WASTE"
    RAW_VEG_TRIMMINGS = "RAW_VEG_TRIMMINGS"


class Destination(StrEnum):
    NGO = "NGO"
    CATTLE_FEED = "CATTLE_FEED"
    BIOGAS = "BIOGAS"
    COMPOST = "COMPOST"
    LANDFILL = "LANDFILL"


# ---- Small shared responses ----

class CsrfOut(ApiModel):
    csrf_token: str


class HealthOut(ApiModel):
    status: str
    db: str
    server_now: IstDateTime
