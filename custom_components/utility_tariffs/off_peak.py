"""The off-peak stretches of a tariff: the times its lowest import price is in force.

Off-peak means the lowest import price held, not any band below the day's average. A tariff whose
held prices are all the same has no off-peak, and neither does one that follows a price feed,
because every half hour of a feed has its own price.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from utility_tariffs_lib.tariff import PriceSlot


@dataclass(frozen=True)
class Stretch:
    """One unbroken time at the off-peak price."""

    start: datetime
    end: datetime


def off_peak_stretches(slots: Sequence[PriceSlot]) -> list[Stretch] | None:
    """The off-peak stretches in time order, or None when the tariff has no off-peak.

    Slots that meet at the same price are joined, so a stretch that runs over midnight is one.
    """
    if not slots or len({slot.import_price for slot in slots}) < 2:
        return None
    lowest = min(slot.import_price for slot in slots)
    stretches: list[Stretch] = []
    for slot in sorted(slots, key=lambda item: item.start):
        if slot.import_price != lowest:
            continue
        if stretches and stretches[-1].end >= slot.start:
            stretches[-1] = Stretch(stretches[-1].start, max(stretches[-1].end, slot.end))
        else:
            stretches.append(Stretch(slot.start, slot.end))
    return stretches


def around(stretches: Sequence[Stretch], now: datetime) -> tuple[Stretch | None, Stretch | None]:
    """The stretch under way at *now*, and the next one that starts after it."""
    current = next((s for s in stretches if s.start <= now < s.end), None)
    upcoming = next((s for s in stretches if s.start > now), None)
    return current, upcoming
