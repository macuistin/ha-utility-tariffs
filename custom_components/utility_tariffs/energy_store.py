"""The half-hourly energy history, saved in a Home Assistant store of its own for each plan.

It has its own store because a year of slots is large. A write is queued when a new half hour
starts, and Home Assistant also writes at shutdown. Nothing is written before the saved history
has been read, so a start-up never replaces it with an empty one.
"""

from __future__ import annotations

import logging
from datetime import datetime, tzinfo
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store
from utility_tariffs_lib.tariff.defaults import SLOT_SECONDS
from utility_tariffs_lib.tariff.slot_history import SlotHistory
from utility_tariffs_lib.tariff.slots import SlotEnergy, local_midnight
from utility_tariffs_lib.timeutil import elapsed_seconds

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
_VERSION = 1
_SAVE_DELAY_SECONDS = 15


def storage_key(entry_id: str) -> str:
    return f"{DOMAIN}.energy_slots_{entry_id}"


class EnergyStore:
    """The slot history of one plan and its storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str, tz: tzinfo) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, _VERSION, storage_key(entry_id))
        self._tz = tz
        self.history = SlotHistory(tz)
        self._loaded = False
        self._saved_slot: tuple[object, int] | None = None

    async def async_load(self) -> None:
        """Read the saved history. A missing or unreadable file starts a fresh one."""
        try:
            data = await self._store.async_load()
            if data is not None:
                self.history.restore(list(data.get("days", [])))
                if self.history.skipped:
                    _LOGGER.warning("Skipped %d unreadable energy days", self.history.skipped)
        except (OSError, ValueError, TypeError, AttributeError) as err:
            _LOGGER.warning("Could not restore the energy history, starting fresh: %s", err)
            self.history = SlotHistory(self._tz)
        finally:
            self._loaded = True

    def record(self, energy: SlotEnergy, start: datetime, end: datetime) -> None:
        """Book energy used from *start* to *end*, and queue a save when a new half hour began."""
        if not self.history.record(energy, start, end):
            return
        slot = self._slot_of(end)
        if slot != self._saved_slot:
            self._saved_slot = slot
            self.schedule_save()

    def record_soc(self, moment: datetime, percent: float) -> None:
        """Note the battery charge. A reading outside 0 to 100 is not a charge and is ignored."""
        if 0 <= percent <= 100:
            self.history.record_soc(moment, percent)

    def schedule_save(self) -> None:
        if self._loaded:
            self._store.async_delay_save(self._payload, _SAVE_DELAY_SECONDS)

    async def async_save(self) -> None:
        if self._loaded:
            await self._store.async_save(self._payload())

    async def async_remove(self) -> None:
        await self._store.async_remove()

    def _slot_of(self, moment: datetime) -> tuple[object, int]:
        since = elapsed_seconds(
            local_midnight(moment.astimezone(self._tz).date(), self._tz), moment
        )
        return moment.astimezone(self._tz).date(), int(since // SLOT_SECONDS)

    def _payload(self) -> dict[str, Any]:
        return {"version": _VERSION, "days": list(self.history.to_storage())}
