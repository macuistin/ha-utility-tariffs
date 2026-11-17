"""price_series.py: a price for each interval of a run of days, and the cost of kWh against it.

A dynamic tariff has no band price, so the bill engine cannot price its energy from band totals.
This is the step before the engine: it looks up the price of each slot in a series (read from the
price day files in the store) and adds up kWh times price. The engine takes that total through a
`series_energy` node. A slot with no price in the series is refused, never priced as zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from .defaults import SLOT_SECONDS
from .definition import SeriesEnergy, TariffDefinition

_UTC = timezone.utc


class MissingPrice(ValueError):
    """A slot falls outside the prices the series holds."""


@dataclass(frozen=True)
class PriceSeries:
    """Prices of consecutive equal intervals from *start*, in the currency's major unit per kWh."""

    start: datetime  # aware
    interval: timedelta
    prices: tuple[Decimal, ...]

    @property
    def end(self) -> datetime:
        return self.start + self.interval * len(self.prices)

    def price_at(self, moment: datetime) -> Decimal:
        """The price of the interval that holds *moment* (aware)."""
        if not self.start <= moment < self.end:
            raise MissingPrice(f"no price at {moment.isoformat()}, the series covers "
                               f"{self.start.isoformat()} to {self.end.isoformat()}")
        return self.prices[(moment - self.start) // self.interval]


def _midnight(day: str, zone: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), time(0), ZoneInfo(zone)).astimezone(_UTC)


def series_from_days(days: Sequence[Mapping[str, Any]]) -> PriceSeries:
    """One series from price day files (as read from JSON), which must follow one another.

    Each day starts at its local midnight, so a clock change makes a day of 23 or 25 hours and the
    next day still begins where this one ends. A gap, an overlap or a changed interval raises."""
    if not days:
        raise ValueError("a price series needs at least one day")
    ordered = sorted(days, key=lambda d: str(d["date"]))
    interval = timedelta(minutes=int(ordered[0]["interval_minutes"]))
    start = _midnight(str(ordered[0]["date"]), str(ordered[0]["timezone"]))
    prices: list[Decimal] = []
    for doc in ordered:
        if timedelta(minutes=int(doc["interval_minutes"])) != interval:
            raise ValueError(f"{doc['date']}: the interval changes within the series")
        if _midnight(str(doc["date"]), str(doc["timezone"])) != start + interval * len(prices):
            raise ValueError(f"{doc['date']}: does not follow the day before it")
        prices += [Decimal(p) for p in doc["prices"]]
    return PriceSeries(start, interval, tuple(prices))


def _slot_price(series: PriceSeries, start: datetime, length: timedelta) -> Decimal:
    """The price of a slot: each interval it touches, weighted by the time it covers."""
    total, cursor, end = Decimal(0), start, start + length
    while cursor < end:
        offset = (cursor - series.start) // series.interval
        edge = min(end, series.start + series.interval * (offset + 1))
        total += series.price_at(cursor) * Decimal((edge - cursor).total_seconds())
        cursor = edge
    return total / Decimal(length.total_seconds())


def series_cost(
    slots: Iterable[tuple[datetime, Decimal]],
    series: PriceSeries,
    slot_seconds: int = SLOT_SECONDS,
) -> Decimal:
    """kWh times price over *slots*, each given as (start, kWh imported).

    A slot longer than the series interval takes the time-weighted average of the intervals it
    covers. The total is not rounded: the bill node rounds it."""
    length = timedelta(seconds=slot_seconds)
    return sum((kwh * _slot_price(series, start, length) for start, kwh in slots), Decimal(0))


def feed_of(series: str) -> str:
    """The feed id a series name stands for. A series name has underscores where the feed has
    hyphens (`octopus_agile` is the feed `octopus-agile`), and the tariff's area key is the feed's
    area."""
    return series.replace("_", "-")


def _walk(value: object) -> Iterator[object]:
    if is_dataclass(value) and not isinstance(value, type):
        yield value
        for item in fields(value):
            yield from _walk(getattr(value, item.name))
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, tuple | list):
        for child in value:
            yield from _walk(child)


def series_names(definition: TariffDefinition) -> tuple[str, ...]:
    """The price series the bill tree names, in the order they are found. Empty for a tariff with
    fixed prices."""
    found = [node.series for node in _walk(definition.total) if isinstance(node, SeriesEnergy)]
    return tuple(dict.fromkeys(found))


def series_runs(days: Sequence[Mapping[str, Any]]) -> list[PriceSeries]:
    """One series for each unbroken run of days, earliest first. A gap, or a day of another
    interval, ends a run, so the days a feed has is still usable when one day is missing."""
    runs: list[list[Mapping[str, Any]]] = []
    for doc in sorted(days, key=lambda d: str(d["date"])):
        if runs:
            try:
                series_from_days([*runs[-1], doc])
            except ValueError:
                runs.append([doc])
            else:
                runs[-1].append(doc)
        else:
            runs.append([doc])
    return [series_from_days(run) for run in runs]
