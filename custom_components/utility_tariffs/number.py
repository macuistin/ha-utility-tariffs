"""The two percentiles that say what a low and a high price are, changed live from the dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory

from .const import (
    CONF_HIGH_PERCENTILE,
    CONF_LOW_PERCENTILE,
    DEFAULT_HIGH_PERCENTILE,
    DEFAULT_LOW_PERCENTILE,
    MAX_LOW_PERCENTILE,
    MIN_HIGH_PERCENTILE,
)
from .coordinator import TariffConfigEntry, TariffCoordinator
from .entity import TariffEntity, per_fuel

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TariffConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for coordinator, add in per_fuel(entry, async_add_entities):
        add([
            PercentileNumber(coordinator, CONF_LOW_PERCENTILE, DEFAULT_LOW_PERCENTILE, 1,
                             MAX_LOW_PERCENTILE),
            PercentileNumber(coordinator, CONF_HIGH_PERCENTILE, DEFAULT_HIGH_PERCENTILE,
                             MIN_HIGH_PERCENTILE, 99),
        ])


class PercentileNumber(TariffEntity, NumberEntity):
    """A percentile kept in the entry's options. A change reaches the sensors at once, with no
    reload, because they read the options each time they are asked."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(  # noqa: PLR0913
        self, coordinator: TariffCoordinator, key: str, default: int, low: int, high: int
    ) -> None:
        super().__init__(coordinator, key)
        self._key, self._default = key, default
        self._attr_translation_key = key
        self._attr_native_min_value, self._attr_native_max_value = low, high

    @property
    def native_value(self) -> float:
        return float(self.coordinator.fuel.options.get(self._key, self._default))

    async def async_set_native_value(self, value: float) -> None:
        fuel = self.coordinator.fuel
        fuel.async_update(self.hass, {**fuel.data, self._key: int(value)})
        self.coordinator.async_update_listeners()
