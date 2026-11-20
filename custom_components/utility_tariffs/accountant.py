"""Books the energy the user's own meters count into the half-hourly history.

Every minute the import and export meters are read. The rise since the last reading is spread over
the slots it covers, so any plan can later be priced over the same energy. A meter that changes
less often than that books each step in the minute it appears.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from utility_tariffs_lib.tariff import SlotEnergy
from utility_tariffs_lib.tariff.slots import local_midnight

from .backfill import BackfillResult, Filler, async_read_hours, slot_totals
from .const import (
    CONF_BATTERY_SOC,
    CONF_IMPORT_ENERGY,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_MAX_METER_KW,
    DOMAIN,
    METER_TARGETS,
)
from .energy_store import EnergyStore
from .meter import Exclusion, RiseTracker, kwh_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

POLL = timedelta(minutes=1)
ISSUE_ID = "meter_readings_left_out"
# The repair issue stays this long after the last reading that was left out.
ISSUE_HOLD = timedelta(hours=24)


@dataclass(frozen=True)
class MeterSetup:
    """The entities to read, by option key, and the largest rise a meter may show, in kW."""

    entities: dict[str, str]
    max_kw: float = DEFAULT_MAX_METER_KW
    history_start: date | None = None  # the first day to fill from statistics


_REASONS = {
    "too_large": "it rose faster than the largest rise set in the options",
    "negative": "it was negative",
}


class EnergyAccountant:
    """Reads the configured meters and keeps the slot history."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: EnergyStore,
        meters: MeterSetup,
        on_booked: Callable[[], None],
    ) -> None:
        self._hass = hass
        self.store = store
        entities = meters.entities
        self._meters = {key: entity for key, entity in entities.items() if key in METER_TARGETS}
        self._soc_entity = entities.get(CONF_BATTERY_SOC)
        self._trackers = {key: RiseTracker(meters.max_kw) for key in self._meters}
        self._on_booked = on_booked
        self._max_kw = meters.max_kw
        self._history_start = meters.history_start
        self.last_backfill = BackfillResult()

    async def async_start(self) -> Callable[[], None]:
        """Read the saved history, take the first readings and start the minute timer."""
        await self.store.async_load()
        self.sample(dt_util.utcnow())

        @callback
        def tick(now: datetime) -> None:
            self.sample(now)

        return async_track_time_interval(self._hass, tick, POLL)

    async def async_backfill(self, first: date | None = None) -> BackfillResult:
        """Fill half hours nothing was booked for from the meters' hourly statistics.

        Runs from *first*, else the start day in the options, else a year back, up to the start of
        this hour. A half hour booked live is left alone, one filled before is replaced.
        """
        tz = self.store.history.tz
        today = dt_util.now().astimezone(tz).date()
        day = first or self._history_start or today - timedelta(days=DEFAULT_HISTORY_DAYS)
        start = local_midnight(day, tz)
        end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        if start >= end:
            return BackfillResult()
        hours = await async_read_hours(self._hass, self._meters, start, end)
        totals = slot_totals(hours, tz, self._max_kw)
        history = self.store.history
        filler = Filler(history, self.store.backfilled, METER_TARGETS, CONF_IMPORT_ENERGY)
        result = filler.fill(totals)
        if result.slots:
            self.last_backfill = result
            self.store.schedule_save()
            self._on_booked()
        return result

    def sample(self, now: datetime) -> None:
        """Read every meter once and book what each counted since its last reading."""
        booked = False
        for key, entity_id in self._meters.items():
            rise = self._trackers[key].update(kwh_of(self._hass.states.get(entity_id)), now)
            if rise is not None:
                group, name = METER_TARGETS[key]
                energy = SlotEnergy(**{group: {name: rise.kwh}})
                self.store.record(energy, rise.start, rise.end)
                booked = True
        self._note_charge(now)
        self._report_suspect(now)
        if booked:
            self._on_booked()

    def _note_charge(self, now: datetime) -> None:
        """Keep the battery's charge beside the slots, for the value of the energy it holds."""
        if self._soc_entity is None:
            return
        state = self._hass.states.get(self._soc_entity)
        try:
            percent = float(state.state) if state is not None else None
        except ValueError:
            return
        if percent is not None:
            self.store.record_soc(now, percent)

    def excluded(self) -> list[dict[str, str | float | None]]:
        """What was left out of the bill, oldest first, for the diagnostics. No entity ids."""
        rows = [
            (item.at, key, item)
            for key, tracker in self._trackers.items()
            for item in tracker.excluded
        ]
        return [
            {
                "meter": key,
                "reason": item.reason,
                "at": at.isoformat(),
                "kwh": None if item.kwh is None else round(item.kwh, 3),
            }
            for at, key, item in sorted(rows, key=lambda row: row[0])
        ]

    def _report_suspect(self, now: datetime) -> None:
        """Raise a repair issue for the latest reading no meter could have given, else clear it."""
        latest = self._latest_suspect()
        if latest is None or now - latest[1].at > ISSUE_HOLD:
            ir.async_delete_issue(self._hass, DOMAIN, ISSUE_ID)
            return
        entity_id, item = latest
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            ISSUE_ID,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_ID,
            translation_placeholders={
                "meter": entity_id,
                "reason": _REASONS[item.reason],
                "when": dt_util.as_local(item.at).strftime("%Y-%m-%d %H:%M"),
            },
        )

    def _latest_suspect(self) -> tuple[str, Exclusion] | None:
        found = [
            (self._meters[key], tracker.latest_suspect)
            for key, tracker in self._trackers.items()
            if tracker.latest_suspect is not None
        ]
        return max(found, key=lambda pair: pair[1].at, default=None)

    def clear_issue(self) -> None:
        """Remove the repair issue, when the entry unloads."""
        ir.async_delete_issue(self._hass, DOMAIN, ISSUE_ID)
