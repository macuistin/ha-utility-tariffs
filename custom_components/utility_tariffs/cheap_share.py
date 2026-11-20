"""How much of the electricity imported was used at cheap times.

A half hour is cheap when it falls in the tariff's lowest import band. The band of each half hour
comes from the engine (`band_at`) and the price of a band from `marginal_prices`, so no price is
multiplied by energy here. A tariff whose bands all cost the same has nothing cheap to use, so its
share is 0, which is a figure and not an unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone
from typing import TYPE_CHECKING

from utility_tariffs_lib.tariff import band_at
from utility_tariffs_lib.tariff.defaults import SLOT_SECONDS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from datetime import date
    from decimal import Decimal

    from utility_tariffs_lib.tariff import SlotDay, TariffDefinition


@dataclass(frozen=True)
class CheapShare:
    """The energy imported at cheap times and in all, in kWh."""

    cheap_kwh: float
    total_kwh: float

    @property
    def percent(self) -> float:
        """The cheap share of all imported energy, 0 when nothing was imported."""
        return 100.0 * self.cheap_kwh / self.total_kwh if self.total_kwh > 0 else 0.0


def cheap_bands(
    import_prices: Mapping[str, Decimal], average: Decimal | None = None
) -> frozenset[str]:
    """The bands that count as cheap, or none when every band costs the same.

    Without an *average* the cheap bands are those at the lowest import price. With one, they are
    those priced at or below it.
    """
    if len(set(import_prices.values())) < 2:
        return frozenset()
    limit = min(import_prices.values()) if average is None else average
    return frozenset(name for name, price in import_prices.items() if price <= limit)


RATING_STEPS = (("very_good", 75.0), ("good", 50.0), ("average", 25.0), ("poor", 0.0))
RATINGS = tuple(name for name, _ in RATING_STEPS)


def share_rating(percent: float) -> str:
    """A label for a cheap share: very good from 75%, good from 50%, average from 25%, else poor."""
    return next(name for name, floor in RATING_STEPS if percent >= floor)


def cheap_share(
    days: Sequence[SlotDay],
    definition: TariffDefinition,
    is_holiday: Callable[[date], bool],
    cheap: frozenset[str],
) -> CheapShare:
    """The imported energy of *days* that fell in a cheap band, and all of it."""
    cheap_kwh = total_kwh = 0.0
    for day in days:
        start = day.start.astimezone(timezone.utc)
        for index, kwh in enumerate(day.flows["import"]):
            if not kwh:
                continue
            slot_start = start + timedelta(seconds=index * SLOT_SECONDS)
            total_kwh += kwh
            if band_at(definition, slot_start, is_holiday) in cheap:
                cheap_kwh += kwh
    return CheapShare(cheap_kwh, total_kwh)
