"""Holds the followed tariff and its prices for the next two days.

The definition is read from the store at start-up and every night shortly after midnight. A store
that cannot be read changes nothing: the prices already held keep working. Sensors work out the
current slot from the held prices, so the coordinator also wakes them at every half hour.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_change, async_track_utc_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_AREA, CONF_COUNTRY, CONF_PROVIDER, CONF_TARIFF, DOMAIN
from .lib.tariff import PriceSlot, TariffDefinition, no_holidays, price_curve
from .lib.tariffstore import StoreError
from .store import store_access

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .accountant import EnergyAccountant
    from .helper.store_access import TariffStoreAccess

_LOGGER = logging.getLogger(__name__)
HORIZON_DAYS = 2  # today and tomorrow, so the next change is always in view
STORE_ERRORS = (StoreError, OSError, ValueError, KeyError, TypeError)
type TariffConfigEntry = ConfigEntry[TariffCoordinator]


@dataclass(frozen=True)
class TariffData:
    """The tariff in force and its prices from local midnight for two days."""

    definition: TariffDefinition
    slots: tuple[PriceSlot, ...]
    holidays_known: bool  # False when the store holds no public holidays for the period
    is_holiday: Callable[[date], bool] = no_holidays

    def slot_at(self, moment: datetime) -> PriceSlot | None:
        for slot in self.slots:
            if slot.start <= moment < slot.end:
                return slot
        return None

    def next_change(self, moment: datetime) -> PriceSlot | None:
        """The first slot that starts after *moment* with a different import price."""
        current = self.slot_at(moment)
        for slot in self.slots:
            if slot.start > moment and (
                current is None or (slot.import_band, slot.import_price)
                != (current.import_band, current.import_price)
            ):
                return slot
        return None


class TariffCoordinator(DataUpdateCoordinator[TariffData]):
    """Reads the tariff and keeps its price series."""

    config_entry: TariffConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TariffConfigEntry,
        access: TariffStoreAccess | None = None,
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None
        )
        self._access = access if access is not None else store_access(hass)
        # Set at start-up when the user has chosen an energy meter. None means no bill is kept.
        self.accountant: EnergyAccountant | None = None

    async def _async_setup(self) -> None:
        """Read again every night, and wake the sensors at every half hour."""

        @callback
        def tick(_now: datetime) -> None:
            if self.data is not None:
                self.async_update_listeners()

        @callback
        def nightly(_now: datetime) -> None:
            self.config_entry.async_create_background_task(
                self.hass, self.async_request_refresh(), "utility_tariffs nightly read"
            )

        self.config_entry.async_on_unload(
            async_track_utc_time_change(self.hass, tick, minute=(0, 30), second=0)
        )
        self.config_entry.async_on_unload(
            async_track_time_change(self.hass, nightly, hour=0, minute=5, second=0)
        )

    async def _async_update_data(self) -> TariffData:
        today = dt_util.now().date()
        try:
            return await self._read(today)
        except STORE_ERRORS as err:
            if self.data is not None:
                _LOGGER.warning("The tariff store could not be read, keeping saved prices: %s", err)
                return self.data
            raise UpdateFailed(f"The tariff store could not be read: {err}") from err

    async def _read(self, today: date) -> TariffData:
        entry = self.config_entry.data
        definition = await self._access.async_definition(
            entry[CONF_COUNTRY], entry[CONF_PROVIDER], entry[CONF_TARIFF], today,
            area=entry[CONF_AREA],
        )
        holidays_known = True
        try:
            is_holiday = await self._access.async_is_holiday(
                entry[CONF_COUNTRY], definition.region
            )
        except StoreError:
            is_holiday, holidays_known = no_holidays, False
        midnight = datetime.min.time()
        start = datetime.combine(today, midnight, definition.timezone)
        end = datetime.combine(
            today + timedelta(days=HORIZON_DAYS), midnight, definition.timezone
        )
        try:
            slots = await self.hass.async_add_executor_job(
                price_curve, definition, start, end, is_holiday
            )
        except StoreError:  # a year the store holds no holidays for
            holidays_known = False
            slots = await self.hass.async_add_executor_job(
                price_curve, definition, start, end, no_holidays
            )
        return TariffData(definition, slots, holidays_known, is_holiday)
