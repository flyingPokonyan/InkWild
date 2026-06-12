from datetime import UTC, datetime, timedelta

BEIJING_UTC_OFFSET = timedelta(hours=8)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def serialize_utc_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def beijing_day_start_utc(now: datetime | None = None) -> datetime:
    """Return today's Beijing 00:00 expressed as naive UTC for DB filters."""
    current = now or utcnow()
    beijing_now = current + BEIJING_UTC_OFFSET
    beijing_midnight = beijing_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return beijing_midnight - BEIJING_UTC_OFFSET


def beijing_date(value: datetime) -> str:
    return (value + BEIJING_UTC_OFFSET).date().isoformat()
