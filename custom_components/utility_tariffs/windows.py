"""Choosing the search for the cheapest and dearest windows from the held prices.

The search itself is `find_window` in the copied tariff library. This only decides which part of
the held prices it may use, so that a window already under way still counts as the current one.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from .coordinator import TariffData
from .lib.tariff import Window, WindowSearch, find_window
from .lib.tariff.defaults import SLOT_SECONDS

# A window that ends sooner than this is treated as over, so the answer does not jump to a later
# window in the last minutes of the cheapest one.
MIN_REMAINING = timedelta(minutes=5)


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
    )
    return find_window(data.slots, search)


def _on_grid(moment: datetime) -> datetime:
    """The next half hour on the engine's grid, counted from the Unix epoch."""
    slot = SLOT_SECONDS
    return datetime.fromtimestamp(math.ceil(moment.timestamp() / slot) * slot, moment.tzinfo)
