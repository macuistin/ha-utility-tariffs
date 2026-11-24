"""Whether the cheapest or the dearest window is under way now."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES
from .coordinator import TariffConfigEntry
from .entity import TariffEntity, per_fuel
from .info_sensor import info_binary_sensors
from .off_peak import around, off_peak_stretches
from .windows import current_window

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TariffConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for data, add in per_fuel(entry, async_add_entities):
        add(
            [
                CheapestWindowActive(data, "cheapest_window_active"),
                DearestWindowActive(data, "dearest_window_active"),
                OffPeak(data, "off_peak"),
            ]
        )
        add(info_binary_sensors(data))
        if data.data.on_a_feed:  # only a published price can fall below zero
            add([NegativePrice(data, "negative_price")])


class _WindowActive(TariffEntity, BinarySensorEntity):
    """On while the current window is under way. A window already begun counts as current."""

    _highest = False

    @property
    def is_on(self) -> bool | None:
        minutes = self.coordinator.fuel.options.get(
            CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES
        )
        now = dt_util.now()
        window = current_window(self.coordinator.data, now, minutes, highest=self._highest)
        return None if window is None else window.start <= now < window.end


class CheapestWindowActive(_WindowActive):
    """On while the current cheapest window is under way."""

    _attr_translation_key = "cheapest_window_active"


class DearestWindowActive(_WindowActive):
    """On while the current dearest window is under way."""

    _attr_translation_key = "dearest_window_active"
    _highest = True


class OffPeak(TariffEntity, BinarySensorEntity):
    """On while the tariff's lowest import price is in force.

    Unavailable for a tariff with one price all day, or one that follows a price feed, because
    neither has an off-peak period.
    """

    _attr_translation_key = "off_peak"

    def _around(self) -> tuple[datetime | None, datetime | None, datetime | None, datetime | None]:
        data = self.coordinator.data
        stretches = None if data.on_a_feed else off_peak_stretches(data.slots)
        if stretches is None:
            return (None, None, None, None)
        current, upcoming = around(stretches, dt_util.now())
        return (
            current.start if current else None,
            current.end if current else None,
            upcoming.start if upcoming else None,
            upcoming.end if upcoming else None,
        )

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        has_off_peak = not data.on_a_feed and off_peak_stretches(data.slots) is not None
        return super().available and has_off_peak

    @property
    def is_on(self) -> bool:
        return self._around()[0] is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        keys = ("current_start", "current_end", "next_start", "next_end")
        return {
            key: moment.isoformat() if moment else None
            for key, moment in zip(keys, self._around(), strict=True)
        }


class NegativePrice(TariffEntity, BinarySensorEntity):
    """On while the import price in force is below zero, so a load can be run to be paid for it.

    Unavailable when no price is held for now, never off by guess.
    """

    _attr_translation_key = "negative_price"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.slot_at(dt_util.now()) is not None

    @property
    def is_on(self) -> bool | None:
        slot = self.coordinator.data.slot_at(dt_util.now())
        return None if slot is None else slot.import_price < 0
