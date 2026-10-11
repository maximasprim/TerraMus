"""Calendar-month helpers shared by the tenant and platform analytics.

Months are keyed "YYYY-MM". Series are always zero-filled over the whole window
so a chart never silently skips a month that simply had no activity.
"""
from datetime import date


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def month_keys(end: date, months: int) -> list[str]:
    """`months` consecutive month keys, oldest first, the last being end's month."""
    keys = []
    for back in range(months - 1, -1, -1):
        y, m = shift_month(end.year, end.month, -back)
        keys.append(f"{y:04d}-{m:02d}")
    return keys


def month_start(key: str) -> date:
    y, m = key.split("-")
    return date(int(y), int(m), 1)


def key_of(year, month) -> str:
    """Build a key from SQL EXTRACT() results (which may come back as Decimal/float)."""
    return f"{int(year):04d}-{int(month):02d}"
