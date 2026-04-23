from datetime import UTC, datetime


def now_utc() -> datetime:
    """Return current time as naive UTC (no tzinfo). Store consistently in TIMESTAMP WITHOUT TZ columns."""
    return datetime.now(UTC).replace(tzinfo=None)
