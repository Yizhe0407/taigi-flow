from datetime import UTC, datetime


def now_utc() -> datetime:
    """Return naive UTC datetime for TIMESTAMP WITHOUT TZ columns."""
    return datetime.now(UTC).replace(tzinfo=None)
