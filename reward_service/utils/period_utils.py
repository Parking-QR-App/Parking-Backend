from datetime import datetime, timedelta
from typing import Literal


def get_start_date_from_period(
    period: Literal["daily", "weekly", "monthly"]
) -> datetime:
    """
    Returns the datetime corresponding to the beginning of the period.
    """
    now = datetime.now()
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError("Unsupported period value")
