"""Diagnostic entities that say which tariff is followed, when its prices apply and how fresh the
data is. Only the store's own dates and the time of our last read are shown."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from homeassistant.components.binary_sensor import (  # type: ignore[attr-defined]
    BinarySensorDeviceClass,  # the `const` module it lives in is missing from older Home Assistant
    BinarySensorEntity,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .const import CONF_MANUAL
from .coordinator import TariffCoordinator
from .entity import TariffEntity
from .forecast import band_prices


class _Diagnostic(TariffEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TariffCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key


class ValidFromSensor(_Diagnostic, SensorEntity):
    """The day the prices now in force start to apply."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "valid_from")

    @property
    def native_value(self) -> date:
        return self.coordinator.data.definition.effective_from


class ValidToSensor(_Diagnostic, SensorEntity):
    """The day the prices stop applying. Unknown while the store holds no end date."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "valid_to")

    @property
    def native_value(self) -> date | None:
        return self.coordinator.data.definition.effective_to


class PricesLastReadSensor(_Diagnostic, SensorEntity):
    """When this install last read the store successfully."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "prices_last_read")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.read_at


class TariffSummarySensor(_Diagnostic, SensorEntity):
    """The followed plan by name, with everything that identifies it in the attributes."""

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "tariff_summary")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.definition.name

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        data = self.coordinator.data
        definition = data.definition
        return {
            "provider": definition.provider.name,
            "country": definition.country,
            "country_availability": data.country_availability,
            "country_reason": data.country_reason,
            "region": definition.region,
            "currency": definition.currency,
            "revision": definition.revision,
            "valid_from": definition.effective_from.isoformat(),
            "valid_to": None if definition.effective_to is None
            else definition.effective_to.isoformat(),
            "source_url": definition.source_url,
            "complete": definition.complete,
            "own_rates": CONF_MANUAL in self.coordinator.config_entry.data,
            "price_feeds": list(data.feeds),
            "import_prices": band_prices(definition),
            "prices_last_read": None if data.read_at is None else data.read_at.isoformat(),
            "store_offline": self.coordinator.access.offline,
        }


class TomorrowPricesAvailable(_Diagnostic, BinarySensorEntity):
    """On once the prices held reach the end of tomorrow. Only for a tariff on a price feed."""

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "tomorrow_prices_available")

    @property
    def is_on(self) -> bool:
        return self.coordinator.tomorrow_known(dt_util.now())


class StoreOffline(_Diagnostic, BinarySensorEntity):
    """On when the last read was answered from saved files because the store was unreachable."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "store_offline")

    @property
    def is_on(self) -> bool:
        return self.coordinator.access.offline


def info_sensors(coordinator: TariffCoordinator) -> list[SensorEntity]:
    """The diagnostic sensors. A household's own rates have no store dates to show."""
    entities: list[SensorEntity] = [
        PricesLastReadSensor(coordinator), TariffSummarySensor(coordinator)
    ]
    if CONF_MANUAL not in coordinator.config_entry.data:
        entities += [ValidFromSensor(coordinator), ValidToSensor(coordinator)]
    return entities


def info_binary_sensors(coordinator: TariffCoordinator) -> list[BinarySensorEntity]:
    """The diagnostic binary sensors. Tomorrow's prices matter only on a price feed."""
    entities: list[BinarySensorEntity] = [StoreOffline(coordinator)]
    if coordinator.data.on_a_feed:
        entities.append(TomorrowPricesAvailable(coordinator))
    return entities
