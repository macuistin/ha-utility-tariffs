"""Choosing the search for the cheapest and dearest windows from the held prices.

The search itself is `find_window` in the tariff library. This only decides which part of
the held prices it may use, so that a window already under way still counts as the current one.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta

from utility_tariffs_lib.tariff import PriceSlot, Window, WindowSearch, find_window
from utility_tariffs_lib.tariff.defaults import SLOT_SECONDS

from .coordinator import TariffData

# A window that ends sooner than this is treated as over, so the answer does not jump to a later
# window in the last minutes of the cheapest one.
MIN_REMAINING = timedelta(minutes=5)
SEARCH_DAYS = 2  # today and tomorrow: the prices are held further ahead, but a window is for soon


def end_of_tomorrow(data: TariffData, now: datetime) -> datetime:
    """The local midnight that ends tomorrow, which is as far as a window is searched by default."""
    zone = data.definition.timezone
    day = now.astimezone(zone).date() + timedelta(days=SEARCH_DAYS)
    return datetime.combine(day, datetime.min.time(), zone)


def current_window(
    data: TariffData, now: datetime, minutes: int, *, highest: bool = False
) -> Window | None:
    """The cheapest (or dearest) window that is under way or still to come.

    Windows may start before *now* as long as they end at least five minutes after it. The
    earliest start is rounded up to the engine's half-hour grid, so a window never begins at an
    odd minute that only comes from the time of the search.
    """
    duration = timedelta(minutes=minutes)
    search = WindowSearch(
        duration=duration,
        highest=highest,
        earliest_start=_on_grid(now - duration + MIN_REMAINING),
        latest_end=end_of_tomorrow(data, now),
    )
    window = find_window(data.slots, search)
    if window is None:
        return None
    return replace(window, end=_run_end(data.slots, window))


def _run_end(slots: tuple[PriceSlot, ...], window: Window) -> datetime:
    """The end of the unbroken run of the window's price that the window sits in.

    The search finds a fixed length, so a window inside a longer band would end part way through
    it. The end follows the band to where the price changes, so it matches the start.
    """
    end = window.end
    price = None
    for slot in slots:
        if price is None:
            if slot.start <= window.start < slot.end:
                price = slot.import_price
                end = max(end, slot.end)
        elif slot.start <= end and slot.import_price == price:
            end = max(end, slot.end)
        elif slot.start > end:
            break
    return end


def _on_grid(moment: datetime) -> datetime:
    """The next half hour on the engine's grid, counted from the Unix epoch."""
    slot = SLOT_SECONDS
    return datetime.fromtimestamp(math.ceil(moment.timestamp() / slot) * slot, moment.tzinfo)
