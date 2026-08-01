# -*- coding: utf-8 -*-
"""Datetime serialization helpers used by API-facing models."""

from datetime import datetime, timezone
from typing import Optional


def serialize_utc_datetime(value: Optional[datetime]) -> Optional[str]:
    """Serialize a database datetime as an explicit UTC ISO-8601 value.

    The database currently stores UTC values in timezone-naive ``DateTime``
    columns for SQLite/PostgreSQL compatibility. A naive value therefore
    means UTC in this application and must be marked with ``Z`` before it is
    sent to browsers; otherwise browsers interpret it as local time.
    """
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")
