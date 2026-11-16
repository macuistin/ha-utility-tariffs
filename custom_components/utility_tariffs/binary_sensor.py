"""Whether the cheapest window is under way now."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES
from .coordinator import TariffConfigEntry
from .entity import TariffEntity
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
    async_add_entities([CheapestWindowActive(entry.runtime_data, "cheapest_window_active")])


class CheapestWindowActive(TariffEntity, BinarySensorEntity):
    """On while the current cheapest window is under way."""

    _attr_translation_key = "cheapest_window_active"

    @property
    def is_on(self) -> bool | None:
        minutes = self.coordinator.config_entry.options.get(
            CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES
        )
        now = dt_util.now()
        window = current_window(self.coordinator.data, now, minutes)
        return None if window is None else window.start <= now < window.end
