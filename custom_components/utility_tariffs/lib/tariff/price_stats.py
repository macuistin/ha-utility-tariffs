"""price_stats.py: the lowest, highest and average price over a time range, and a rating.

The statistics read a price series from `price_curve`, so every tax and discount is already in.
The average is weighted by time, because slots can be of any length. A range the series does not
cover in full still gets statistics from the part it does cover, and says so in `complete`.

The rating places a price inside the range's own lowest to highest span, in five equal steps.
That makes it comparable across tariffs and countries: it says how a price compares with the
rest of the day, not whether it is cheap in money. A range with one price has no span, so every
price in it rates as normal.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from .price_curve import PriceSlot

POINTS = (10, 50, 90)  # the percentiles that say what low, middle and high look like
MIN_WINDOW = timedelta(hours=6)  # least prices a window needs before its percentiles show
MIN_PERCENT, MAX_PERCENT = 1, 99  # the percentiles a caller may ask for
MIN_HISTORY_DAYS = 7  # least past days the same time of day needs before its percentiles show
HISTORY_DAYS = 28
PART_OF_DAY = timedelta(hours=4)  # the stretch of each past day that is compared
LEVELS = ("low", "mid", "high")
RATINGS = ("very_low", "low", "normal", "high", "very_high")
type Rating = Literal["very_low", "low", "normal", "high", "very_high"]
type Level = Literal["low", "mid", "high"]


@dataclass(frozen=True)
class PriceStats:
    """The prices over a range, per kWh."""

    lowest: Decimal
    highest: Decimal
    average: Decimal  # weighted by the time each price is in force
    complete: bool  # False when the series does not cover the whole range


def price_stats(
    slots: Sequence[PriceSlot],
    start: datetime,
    end: datetime,
    flow: Literal["import", "export"] = "import",
) -> PriceStats | None:
    """The statistics of *flow* prices from *start* to *end*, or None when none are held."""
    if end <= start:
        raise ValueError("end must be after start")
    prices: list[tuple[Decimal, Decimal]] = []  # (price, seconds in force)
    for slot in slots:
        seconds = (min(slot.end, end) - max(slot.start, start)).total_seconds()
        if seconds > 0:
            price = slot.import_price if flow == "import" else slot.export_price
            prices.append((price, Decimal(str(seconds))))
    if not prices:
        return None
    covered = sum((seconds for _, seconds in prices), Decimal(0))
    weighted = sum((price * seconds for price, seconds in prices), Decimal(0))
    return PriceStats(
        lowest=min(price for price, _ in prices),
        highest=max(price for price, _ in prices),
        average=weighted / covered,
        complete=covered == Decimal(str((end - start).total_seconds())),
    )


def price_rating(price: Decimal, stats: PriceStats) -> Rating:
    """Where *price* sits between the lowest and highest price of *stats*, in five steps."""
    span = stats.highest - stats.lowest
    if span <= 0:
        return "normal"
    position = (price - stats.lowest) / span
    step = min(int(position * len(RATINGS)), len(RATINGS) - 1)
    return RATINGS[max(step, 0)]  # type: ignore[return-value]


def _weighted(
    slots: Sequence[PriceSlot], start: datetime, end: datetime, flow: str,
) -> list[tuple[Decimal, Decimal]]:
    """(price, seconds in force) for each slot part inside the range."""
    found: list[tuple[Decimal, Decimal]] = []
    for slot in slots:
        seconds = (min(slot.end, end) - max(slot.start, start)).total_seconds()
        if seconds > 0:
            price = slot.import_price if flow == "import" else slot.export_price
            found.append((price, Decimal(str(seconds))))
    return found


def _percentiles(
    weighted: list[tuple[Decimal, Decimal]], points: Sequence[int],
) -> dict[int, Decimal]:
    """The price at each percentile by time: the lowest price for which at least that share of
    the time is at or below it (nearest rank)."""
    ordered = sorted(weighted)
    total = sum((seconds for _, seconds in ordered), Decimal(0))
    result: dict[int, Decimal] = {}
    for point in points:
        wanted, running = total * Decimal(point) / Decimal(100), Decimal(0)
        for price, seconds in ordered:
            running += seconds
            if running >= wanted:
                result[point] = price
                break
    return result


def price_percentiles(  # noqa: PLR0913
    slots: Sequence[PriceSlot],
    start: datetime,
    end: datetime,
    flow: Literal["import", "export"] = "import",
    points: Sequence[int] = POINTS,
) -> dict[int, Decimal] | None:
    """The percentiles of *flow* prices over a range, weighted by time, or None when the slots
    cover less than `MIN_WINDOW` of it. A long price counts for as long as it is in force."""
    if end <= start:
        raise ValueError("end must be after start")
    weighted = _weighted(slots, start, end, flow)
    if sum((seconds for _, seconds in weighted), Decimal(0)) < Decimal(
            str(MIN_WINDOW.total_seconds())):
        return None
    return _percentiles(weighted, points)


@dataclass(frozen=True)
class HistoryPercentiles:
    """The percentiles of the same part of the day over past days, and how many days they use."""

    points: dict[int, Decimal]
    days: int


def history_percentiles(  # noqa: PLR0913
    slots: Sequence[PriceSlot],
    moment: datetime,
    flow: Literal["import", "export"] = "import",
    look_back: int = HISTORY_DAYS,
    points: Sequence[int] = POINTS,
) -> HistoryPercentiles | None:
    """The percentiles of the `PART_OF_DAY` around *moment*'s local time of day, over each of the
    last *look_back* days that the slots cover in full. None when fewer than `MIN_HISTORY_DAYS`
    days qualify.

    Days are counted on the local calendar, so a clock change does not move the time of day."""
    local = moment.astimezone(slots[0].start.tzinfo) if slots else moment
    weighted: list[tuple[Decimal, Decimal]] = []
    days = 0
    for back in range(1, look_back + 1):
        centre = datetime.combine(
            local.date() - timedelta(days=back), local.time(), local.tzinfo)
        part = _weighted(slots, centre - PART_OF_DAY / 2, centre + PART_OF_DAY / 2, flow)
        covered = sum((seconds for _, seconds in part), Decimal(0))
        if covered == Decimal(str(PART_OF_DAY.total_seconds())):
            weighted += part
            days += 1
    if days < MIN_HISTORY_DAYS:
        return None
    return HistoryPercentiles(_percentiles(weighted, points), days)


def price_level(price: Decimal, points: dict[int, Decimal], low: int = 10, high: int = 90) -> Level:
    """Low at or below the *low* percentile, high at or above the *high* one, else mid. When the
    two are the same price there is no spread, so the level is mid. A percentile that is not in
    *points* gives mid."""
    floor, ceiling = points.get(low), points.get(high)
    if floor is None or ceiling is None or floor == ceiling:
        return "mid"
    if price <= floor:
        return "low"
    return "high" if price >= ceiling else "mid"


def next_at_or_below(
    slots: Sequence[PriceSlot],
    moment: datetime,
    threshold: Decimal,
    flow: Literal["import", "export"] = "import",
) -> PriceSlot | None:
    """The slot in force at *moment*, or else the first one after it, whose price is at or below
    *threshold*. It is how a percentile becomes "the next cheap time". None when none is held.

    A slot that meets the one before it at the same side of the threshold is not joined, so the
    caller reads the start of a cheap stretch from the first slot it gets back."""
    for slot in sorted(slots, key=lambda item: item.start):
        price = slot.import_price if flow == "import" else slot.export_price
        if slot.end > moment and price <= threshold:
            return slot
    return None
