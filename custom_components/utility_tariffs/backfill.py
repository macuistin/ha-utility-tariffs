"""Fills the half-hourly history from the long-term statistics Home Assistant already holds.

A meter has been counting long before the plan was set up, and while Home Assistant was off. Its
hourly statistics are spread evenly over the two half hours of each hour, so the result is exact
only for a price that does not change within the hour. A half hour that was booked live is never
touched. A half hour filled here may be filled again, so a second run after a meter change
replaces it rather than adding to it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import TYPE_CHECKING

from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.helpers.recorder import get_instance
from utility_tariffs_lib.tariff import SlotEnergy
from utility_tariffs_lib.tariff.defaults import SLOT_SECONDS
from utility_tariffs_lib.tariff.slots import SlotDay, local_midnight
from utility_tariffs_lib.timeutil import elapsed_seconds

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import Any

    from homeassistant.core import HomeAssistant
    from utility_tariffs_lib.tariff import SlotHistory

HOUR_SECONDS = 3600
# A slot counts as read for a series when its hours cover it, give or take a second.
_COMPLETE = SLOT_SECONDS - 1


@dataclass(frozen=True)
class Hour:
    """The energy a meter counted in one hour, in kWh."""

    start: datetime
    kwh: float


@dataclass(frozen=True)
class BackfillResult:
    """What a run filled, for the diagnostics and the action's answer."""

    slots: int = 0
    first: date | None = None
    last: date | None = None


@dataclass
class _Slot:
    kwh: dict[str, float]
    covered: dict[str, float]


type Targets = Mapping[str, tuple[str, str]]  # series key -> (group, name) as in METER_TARGETS


def _new_slot() -> _Slot:
    return _Slot(defaultdict(float), defaultdict(float))


def slot_totals(
    hours: Mapping[str, list[Hour]], tz: tzinfo, max_kw: float
) -> dict[tuple[date, int], _Slot]:
    """The energy of each half hour, by series, and how many seconds of it the hours cover."""
    slots: dict[tuple[date, int], _Slot] = defaultdict(_new_slot)
    for series, rows in hours.items():
        for row in rows:
            if row.kwh < 0 or row.kwh > max_kw:
                continue  # a reset or a jump no supply could deliver: leave the hour unread
            for key, overlap in _pieces(row.start, tz):
                slot = slots[key]
                slot.kwh[series] += row.kwh * overlap / HOUR_SECONDS
                slot.covered[series] += overlap
    return slots


def _pieces(start: datetime, tz: tzinfo) -> list[tuple[tuple[date, int], float]]:
    """The slots an hour overlaps, each with the seconds of overlap."""
    start = start.astimezone(timezone.utc)
    end = start + timedelta(seconds=HOUR_SECONDS)
    pieces = []
    cursor = start
    while cursor < end:
        day = cursor.astimezone(tz).date()
        midnight = local_midnight(day, tz)
        index = int(elapsed_seconds(midnight, cursor) // SLOT_SECONDS)
        slot_end = midnight.astimezone(timezone.utc) + timedelta(seconds=(index + 1) * SLOT_SECONDS)
        next_day = local_midnight(day + timedelta(days=1), tz).astimezone(timezone.utc)
        piece_end = min(end, slot_end, next_day)
        pieces.append(((day, index), elapsed_seconds(cursor, piece_end)))
        cursor = piece_end
    return pieces


class Filler:
    """Writes read half hours into one history, keeping track of which ones it wrote."""

    def __init__(
        self,
        history: SlotHistory,
        marks: dict[date, set[int]],
        targets: Targets,
        required: str,
    ) -> None:
        self._history = history
        self._marks = marks
        self._targets = targets
        self._required = required  # the series that must be read for a half hour to count

    def fill(self, totals: Mapping[tuple[date, int], _Slot]) -> BackfillResult:
        """Write each fully read half hour that was not booked live."""
        filled: list[date] = []
        for (day, index), slot in sorted(totals.items()):
            if slot.covered.get(self._required, 0) < _COMPLETE or not self._writable(day, index):
                continue
            self._write(day, index, slot)
            filled.append(day)
        if not filled:
            return BackfillResult()
        return BackfillResult(len(filled), min(filled), max(filled))

    def _writable(self, day: date, index: int) -> bool:
        held = self._history.get(day)
        return held is None or held.seconds[index] <= 0 or index in self._marks.get(day, ())

    def _write(self, day: date, index: int, slot: _Slot) -> None:
        held = self._day(day, index)
        for series, (group, name) in self._targets.items():
            values = getattr(held, group).setdefault(name, [0.0] * held.slot_count)
            read = slot.covered.get(series, 0) >= _COMPLETE
            values[index] = slot.kwh.get(series, 0.0) if read else 0.0
        held.seconds[index] = float(SLOT_SECONDS)
        self._marks.setdefault(day, set()).add(index)

    def _day(self, day: date, index: int) -> SlotDay:
        held = self._history.get(day)
        if held is None:
            # Booking nothing for one slot is how the history makes the day.
            start = local_midnight(day, self._history.tz).astimezone(timezone.utc)
            start += timedelta(seconds=index * SLOT_SECONDS)
            self._history.record(SlotEnergy(), start, start + timedelta(seconds=SLOT_SECONDS))
            held = self._history.get(day)
        if held is None:
            raise ValueError(f"no history day for {day}")
        return held


async def async_read_hours(
    hass: HomeAssistant, entities: Mapping[str, str], start: datetime, end: datetime
) -> dict[str, list[Hour]]:
    """The hourly change of each meter from the long-term statistics, in kWh.

    *entities* maps a series key to the meter's entity id. An hour the recorder has no figure for
    is left out, so it leaves its half hours unread rather than counting them as zero.
    """
    if "recorder" not in hass.config.components:
        return {}
    ids = set(entities.values())
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start, end, ids, "hour", {"energy": "kWh"}, {"change"}
    )
    return {key: _hours(rows.get(entity_id, [])) for key, entity_id in entities.items()}


def _hours(rows: Iterable[Mapping[str, Any]]) -> list[Hour]:
    found = []
    for row in rows:
        change = row.get("change")
        if change is not None:
            found.append(Hour(datetime.fromtimestamp(row["start"], timezone.utc), float(change)))
    return found
