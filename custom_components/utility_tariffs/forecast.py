"""What the price forecast says: the slots ahead, the percentiles, and the next low or high price.

This reads the held `TariffData` and the two percentiles the user chose. It never touches Home
Assistant, so the entities only format what it returns. All the price maths is in the copied
`utility_tariffs_lib.tariff`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from utility_tariffs_lib.tariff import (
    HistoryPercentiles,
    PriceSlot,
    TariffDefinition,
    history_percentiles,
    marginal_prices,
    next_at_or_below,
    price_level,
    price_percentiles,
)

from .coordinator import TariffData

FORECAST_HOURS = 48  # how much of the forecast is written into the sensor's attributes


@dataclass(frozen=True)
class Percents:
    """The two percentiles the user chose for what counts as a low and a high price."""

    low: int
    high: int

    @property
    def points(self) -> tuple[int, int, int]:
        return (self.low, 50, self.high)


def _price(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def ahead(data: TariffData, now: datetime) -> list[PriceSlot]:
    """The held slots from *now* on (the one in force is cut to start now)."""
    return [slot for slot in data.slots if slot.end > now]


def window_points(data: TariffData, now: datetime, percents: Percents) -> dict[int, Decimal] | None:
    """The percentiles of every price known from *now*, when 6 hours of it are known."""
    known = data.known_until(now)
    if known is None:
        return None
    return price_percentiles(data.slots, now, known, "import", percents.points)


def history_points(
    data: TariffData, now: datetime, percents: Percents
) -> HistoryPercentiles | None:
    """The percentiles of this time of day over the past days, when 7 of them are held."""
    return history_percentiles(data.slots, now, "import", points=percents.points)


def level(data: TariffData, now: datetime, percents: Percents) -> str | None:
    """Low, mid or high for the price now, against the past days' prices at this time of day, or
    against the prices known ahead when there is not enough history yet."""
    slot = data.slot_at(now)
    if slot is None:
        return None
    history = history_points(data, now, percents)
    points = history.points if history else window_points(data, now, percents)
    if points is None:
        return None
    return price_level(slot.import_price, points, percents.low, percents.high)


def _threshold(
    data: TariffData, now: datetime, percents: Percents, *, high: bool
) -> Decimal | None:
    points = window_points(data, now, percents)
    return None if points is None else points.get(percents.high if high else percents.low)


def next_cheap(data: TariffData, now: datetime, percents: Percents) -> dict[str, Any] | None:
    """The next slot at or below the low percentile of the prices known ahead, and when that
    stretch of low prices ends."""
    threshold = _threshold(data, now, percents, high=False)
    if threshold is None:
        return None
    slot = next_at_or_below(data.slots, now, threshold)
    if slot is None:
        return None
    return {"start": max(slot.start, now), "end": _stretch_end(data.slots, slot, threshold),
            "price": slot.import_price, "threshold": threshold}


def next_dear(data: TariffData, now: datetime, percents: Percents) -> dict[str, Any] | None:
    """The next slot at or above the high percentile of the prices known ahead."""
    threshold = _threshold(data, now, percents, high=True)
    if threshold is None:
        return None
    for slot in sorted(data.slots, key=lambda item: item.start):
        if slot.end > now and slot.import_price >= threshold:
            return {"start": max(slot.start, now), "end": _stretch_end(
                data.slots, slot, threshold, above=True), "price": slot.import_price,
                    "threshold": threshold}
    return None


def _stretch_end(
    slots: tuple[PriceSlot, ...], first: PriceSlot, threshold: Decimal, *, above: bool = False
) -> datetime:
    end = first.end
    for slot in sorted(slots, key=lambda item: item.start):
        if slot.start != end:
            continue
        within = slot.import_price >= threshold if above else slot.import_price <= threshold
        if not within:
            break
        end = slot.end
    return end


def slot_rows(data: TariffData, now: datetime, hours: int = FORECAST_HOURS) -> list[dict[str, Any]]:
    """The slots from *now* for *hours*, as plain values for an attribute or a chart."""
    limit = now + timedelta(hours=hours)
    return [
        {
            "start": max(slot.start, now).isoformat(),
            "end": min(slot.end, limit).isoformat(),
            "price": _price(slot.import_price),
            "band": slot.import_band,
            "source": slot.source,
        }
        for slot in ahead(data, now)
        if slot.start < limit
    ]


def band_prices(definition: TariffDefinition) -> dict[str, float | None]:
    """The price of one more kWh in each import band, with every tax and discount in."""
    return {
        band: _price(price)
        for band, price in marginal_prices(definition).import_prices.items()
    }


def revision_rows(data: TariffData, now: datetime) -> list[dict[str, Any]]:
    """The revisions that start after *now*: the day each applies from and each band price."""
    rows = []
    for revision in data.revisions:
        start = datetime.combine(
            revision.first_day, datetime.min.time(), revision.definition.timezone
        )
        if start > now:
            rows.append({
                "effective_from": revision.first_day.isoformat(),
                "import_prices": band_prices(revision.definition),
            })
    return rows


def points_row(points: dict[int, Decimal] | None) -> dict[str, float | None] | None:
    return None if points is None else {f"p{key}": _price(value) for key, value in points.items()}
