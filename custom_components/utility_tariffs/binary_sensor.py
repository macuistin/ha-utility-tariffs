"""Whether the cheapest or the dearest window is under way now."""

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
    data = entry.runtime_data
    async_add_entities(
        [
            CheapestWindowActive(data, "cheapest_window_active"),
            DearestWindowActive(data, "dearest_window_active"),
        ]
    )


class _WindowActive(TariffEntity, BinarySensorEntity):
    """On while the current window is under way. A window already begun counts as current."""

    _highest = False

    @property
    def is_on(self) -> bool | None:
        minutes = self.coordinator.config_entry.options.get(
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
