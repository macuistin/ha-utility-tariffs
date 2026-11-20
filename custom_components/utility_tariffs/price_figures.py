"""Figures of the held prices that need the slots themselves: when the lowest and highest price of
a day start, how far the current price is from the highest, and how many half hours are cheaper.

Everything reads the slots the tariff holds. A day that is not priced in full has no figure,
never a guess.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal

    from utility_tariffs_lib.tariff import PriceSlot

    from .coordinator import TariffData


def _day_bounds(data: TariffData, moment: datetime) -> tuple[datetime, datetime]:
    zone = data.definition.timezone
    day = moment.astimezone(zone).date()
    start = datetime.combine(day, datetime.min.time(), zone)
    return start, datetime.combine(day + timedelta(days=1), datetime.min.time(), zone)


def _day_slots(data: TariffData, moment: datetime) -> list[PriceSlot]:
    """The slots that overlap the local day holding *moment*, oldest first.

    A band that began the evening before still covers the early hours, so overlap counts, not the
    start."""
    start, end = _day_bounds(data, moment)
    return sorted((s for s in data.slots if s.start < end and s.end > start), key=lambda s: s.start)


def extreme_time(data: TariffData, moment: datetime, *, highest: bool) -> datetime | None:
    """When the lowest (or highest) import price of the day first applies, or None while the day
    is not priced in full. A band that began the day before gives the start of the day."""
    stats = data.day_stats(moment, "import")
    if stats is None or not stats.complete:
        return None
    target = stats.highest if highest else stats.lowest
    day_start, _ = _day_bounds(data, moment)
    slot = next((s for s in _day_slots(data, moment) if s.import_price == target), None)
    return None if slot is None else max(slot.start, day_start)


def percent_of_highest(data: TariffData, now: datetime) -> float | None:
    """The import price now as a percentage of the day's highest, or None when it has no meaning."""
    slot = data.slot_at(now)
    stats = data.day_stats(now, "import")
    if slot is None or stats is None or stats.highest <= 0:
        return None
    return float(100 * slot.import_price / stats.highest)


def cheaper_periods(data: TariffData, now: datetime) -> int | None:
    """How many half hours of today cost less than now, or None without a full day's prices."""
    slot = data.slot_at(now)
    stats = data.day_stats(now, "import")
    if slot is None or stats is None or not stats.complete:
        return None
    day_start, day_end = _day_bounds(data, now)
    price: Decimal = slot.import_price
    seconds = sum(
        (min(s.end, day_end) - max(s.start, day_start)).total_seconds()
        for s in _day_slots(data, now)
        if s.import_price < price
    )
    return round(seconds / 1800)
