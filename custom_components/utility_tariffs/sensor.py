"""Price and band sensors of one tariff, read from the held price series."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.util import dt as dt_util

from .coordinator import TariffConfigEntry, TariffCoordinator, TariffData
from .entity import TariffEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TariffSensorDescription(SensorEntityDescription):
    """A sensor and how to read its value from the tariff at a moment."""

    value: Callable[[TariffData, datetime], str | float | datetime | None]
    per_kwh: bool = False  # the unit is the tariff's currency per kWh


def _price(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _current(field: str) -> Callable[[TariffData, datetime], str | float | None]:
    def read(data: TariffData, now: datetime) -> str | float | None:
        slot = data.slot_at(now)
        if slot is None:
            return None
        value = getattr(slot, field)
        return value if isinstance(value, str) else _price(value)

    return read


def _next(field: str) -> Callable[[TariffData, datetime], str | float | datetime | None]:
    def read(data: TariffData, now: datetime) -> str | float | datetime | None:
        slot = data.next_change(now)
        if slot is None:
            return None
        if field == "start":
            return slot.start
        return _price(getattr(slot, field))

    return read


SENSORS = (
    TariffSensorDescription(
        key="import_price",
        translation_key="import_price",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        per_kwh=True,
        value=_current("import_price"),
    ),
    TariffSensorDescription(
        key="export_price",
        translation_key="export_price",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        per_kwh=True,
        value=_current("export_price"),
    ),
    TariffSensorDescription(
        key="import_band", translation_key="import_band", value=_current("import_band")
    ),
    TariffSensorDescription(
        key="next_import_price",
        translation_key="next_import_price",
        suggested_display_precision=4,
        per_kwh=True,
        value=_next("import_price"),
    ),
    TariffSensorDescription(
        key="next_price_change",
        translation_key="next_price_change",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=_next("start"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TariffConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(TariffSensor(coordinator, description) for description in SENSORS)


class TariffSensor(TariffEntity, SensorEntity):
    """One value of the tariff in force now."""

    entity_description: TariffSensorDescription

    def __init__(
        self, coordinator: TariffCoordinator, description: TariffSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.per_kwh:
            self._attr_native_unit_of_measurement = (
                f"{coordinator.data.definition.currency}/kWh"
            )

    @property
    def native_value(self) -> str | float | datetime | None:
        return self.entity_description.value(self.coordinator.data, dt_util.now())
