"""ApiModel (camelCase JSON), IstDateTime (no offset means IST; output in IST) and TempC (a JSON number)."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.clock import IST
from app.schemas.common import ApiModel, BatchStatus, IstDateTime, TempC


class ReadingSample(ApiModel):
    temp_c: TempC
    read_at: IstDateTime
    note: str | None = None


def test_json_keys_are_camel_case():
    reading = ReadingSample(temp_c=Decimal("72.5"), read_at=datetime(2026, 10, 30, 12, 25, tzinfo=IST))
    assert set(reading.model_dump(mode="json")) == {"tempC", "readAt", "note"}


def test_input_accepts_camel_case_and_snake_case():
    a = ReadingSample.model_validate({"tempC": 72.5, "readAt": "2026-10-30T12:25:00+05:30"})
    b = ReadingSample.model_validate({"temp_c": 72.5, "read_at": "2026-10-30T12:25:00+05:30"})
    assert a == b


def test_a_time_without_offset_means_ist():
    reading = ReadingSample.model_validate({"tempC": 70, "readAt": "2026-10-30T12:25:00"})
    assert reading.read_at.utcoffset().total_seconds() == 5.5 * 3600
    assert reading.read_at == datetime(2026, 10, 30, 6, 55, tzinfo=timezone.utc)


def test_times_are_sent_in_ist_and_temperatures_as_numbers():
    utc_value = datetime(2026, 10, 30, 6, 55, tzinfo=timezone.utc)  # how the database returns it
    reading = ReadingSample(temp_c=Decimal("72.5"), read_at=utc_value)
    assert reading.model_dump_json() == '{"tempC":72.5,"readAt":"2026-10-30T12:25:00+05:30","note":null}'


@pytest.mark.parametrize("temp", ["120.5", "-10.5", "72.55"])
def test_temperature_range_and_one_decimal(temp):
    with pytest.raises(ValidationError):
        ReadingSample.model_validate({"tempC": temp, "readAt": "2026-10-30T12:25:00"})


def test_str_enum_member_equals_its_database_string():
    assert BatchStatus.HOLDING == "HOLDING"
