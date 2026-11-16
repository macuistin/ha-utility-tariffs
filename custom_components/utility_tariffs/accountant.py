"""Books the energy the user's own meters count into the half-hourly history.

Every minute the import and export meters are read. The rise since the last reading is spread over
the slots it covers, so any plan can later be priced over the same energy. A meter that changes
less often than that books each step in the minute it appears.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import CONF_BATTERY_SOC, METER_TARGETS
from .energy_store import EnergyStore
from .lib.tariff import SlotEnergy
from .meter import RiseTracker, kwh_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

POLL = timedelta(minutes=1)


class EnergyAccountant:
    """Reads the configured meters and keeps the slot history."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: EnergyStore,
        meters: dict[str, str],
        on_booked: Callable[[], None],
    ) -> None:
        self._hass = hass
        self.store = store
        self._meters = {key: entity for key, entity in meters.items() if key in METER_TARGETS}
        self._soc_entity = meters.get(CONF_BATTERY_SOC)
        self._trackers = {key: RiseTracker() for key in self._meters}
        self._on_booked = on_booked

    async def async_start(self) -> Callable[[], None]:
        """Read the saved history, take the first readings and start the minute timer."""
        await self.store.async_load()
        self.sample(dt_util.utcnow())

        @callback
        def tick(now: datetime) -> None:
            self.sample(now)

        return async_track_time_interval(self._hass, tick, POLL)

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
