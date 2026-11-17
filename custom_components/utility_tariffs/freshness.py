"""When the prices held are old or about to run out, worked out from the data alone."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import TariffData

ENDING_DAYS = 14  # a plan with an end date this close and no later revision is raised
UNREACHED_DAYS = 3  # this long without a read from the store is raised


def plan_ending(data: TariffData, today: date) -> date | None:
    """The day the plan's prices end, when that is near and the store holds nothing after it."""
    end = data.definition.effective_to
    if end is None or len(data.revisions) > 1:
        return None
    return end if end <= today + timedelta(days=ENDING_DAYS) else None


def days_unreached(data: TariffData, now: datetime) -> int | None:
    """Whole days since the store was last read, when that is too long."""
    if data.read_at is None:
        return None
    days = (now - data.read_at).days
    return days if days >= UNREACHED_DAYS else None
