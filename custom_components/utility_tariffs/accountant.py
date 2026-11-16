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

from .const import CONF_EXPORT_ENERGY, CONF_IMPORT_ENERGY
from .energy_store import EnergyStore
from .lib.tariff import SlotEnergy
from .meter import RiseTracker, kwh_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

POLL = timedelta(minutes=1)
FLOW_OF = {CONF_IMPORT_ENERGY: "import", CONF_EXPORT_ENERGY: "export"}


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
        self._meters = {FLOW_OF[key]: entity for key, entity in meters.items() if key in FLOW_OF}
        self._trackers = {flow: RiseTracker() for flow in self._meters}
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
        for flow, entity_id in self._meters.items():
            rise = self._trackers[flow].update(kwh_of(self._hass.states.get(entity_id)), now)
            if rise is not None:
                self.store.record(SlotEnergy(flows={flow: rise.kwh}), rise.start, rise.end)
                booked = True
        if booked:
            self._on_booked()
