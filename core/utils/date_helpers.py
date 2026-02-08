"""
Helpers for parsing date-only query params into timezone-aware datetimes
for filtering (start of day 00:01, end of day 23:59:59).
"""
from datetime import datetime, time

from django.utils import timezone

# Standardized day boundaries for all date filters app-wide
START_OF_DAY_TIME = time(0, 1, 0)  # 00:01 AM
END_OF_DAY_TIME = time(23, 59, 59, 999999)  # 11:59 PM (end of day)


def parse_date_range(start_date_str, end_date_str):
    """
    Parse YYYY-MM-DD start/end strings into timezone-aware datetimes.

    - Start: that day at 00:01:00 (local timezone).
    - End: that day at 23:59:59.999999 (local timezone).

    Returns (start_dt, end_dt) if both strings are present and valid,
    else None. Callers should only apply date filters when result is not None.
    """
    if not start_date_str or not end_date_str:
        return None
    try:
        start_date = datetime.strptime(start_date_str.strip(), '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str.strip(), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None
    start_naive = datetime.combine(start_date, START_OF_DAY_TIME)
    end_naive = datetime.combine(end_date, END_OF_DAY_TIME)
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(start_naive, tz)
    end_dt = timezone.make_aware(end_naive, tz)
    return start_dt, end_dt
