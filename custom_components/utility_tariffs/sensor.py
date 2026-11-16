"""Price and band sensors of one tariff, read from the held price series."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.util import dt as dt_util

from .bill_sensor import BILL_SENSORS, BillSensor
from .const import CONF_HOUSE_ENERGY, CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES
from .coordinator import TariffConfigEntry, TariffCoordinator, TariffData
from .entity import TariffEntity
from .lib.tariff import price_rating
from .lib.tariff.price_stats import RATINGS
from .savings_sensor import SavingsSensor
from .windows import current_window

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TariffSensorDescription(SensorEntityDescription):
    """A sensor and how to read its value from the tariff at a moment."""

    value: Callable[[TariffData, datetime, int], str | float | datetime | None]
    per_kwh: bool = False  # the unit is the tariff's currency per kWh


def _price(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _current(field: str) -> Callable[[TariffData, datetime, int], str | float | None]:
    def read(data: TariffData, now: datetime, _minutes: int) -> str | float | None:
        slot = data.slot_at(now)
        if slot is None:
            return None
        value = getattr(slot, field)
        return value if isinstance(value, str) else _price(value)

    return read


def _next(field: str) -> Callable[[TariffData, datetime, int], str | float | datetime | None]:
    def read(data: TariffData, now: datetime, _minutes: int) -> str | float | datetime | None:
        slot = data.next_change(now)
        if slot is None:
            return None
        if field == "start":
            return slot.start
        return _price(getattr(slot, field))

    return read


def _previous(data: TariffData, now: datetime, _minutes: int) -> float | None:
    slot = data.previous_change(now)
    return None if slot is None else _price(slot.import_price)


def _day(
    flow: Literal["import", "export"], field: str
) -> Callable[[TariffData, datetime, int], float | None]:
    def read(data: TariffData, now: datetime, _minutes: int) -> float | None:
        stats = data.day_stats(now, flow)
        return None if stats is None else _price(getattr(stats, field))

    return read


def _rating(data: TariffData, now: datetime, _minutes: int) -> str | None:
    slot = data.slot_at(now)
    stats = data.day_stats(now, "import")
    if slot is None or stats is None:
        return None
    return price_rating(slot.import_price, stats)


def _window(
    edge: str, *, highest: bool = False
) -> Callable[[TariffData, datetime, int], datetime | None]:
    def read(data: TariffData, now: datetime, minutes: int) -> datetime | None:
        window = current_window(data, now, minutes, highest=highest)
        return None if window is None else getattr(window, edge)

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
        key="previous_import_price",
        translation_key="previous_import_price",
        suggested_display_precision=4,
        per_kwh=True,
        value=_previous,
    ),
    TariffSensorDescription(
        key="import_price_rating",
        translation_key="import_price_rating",
        device_class=SensorDeviceClass.ENUM,
        options=list(RATINGS),
        value=_rating,
    ),
    *(
        TariffSensorDescription(
            key=f"{prefix}_{flow}_price_today",
            translation_key=f"{prefix}_{flow}_price_today",
            suggested_display_precision=4,
            per_kwh=True,
            entity_registry_enabled_default=flow == "import",
            value=_day(flow, field),
        )
        for flow in ("import", "export")
        for prefix, field in (
            ("lowest", "lowest"),
            ("highest", "highest"),
            ("average", "average"),
        )
    ),
    TariffSensorDescription(
        key="next_price_change",
        translation_key="next_price_change",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=_next("start"),
    ),
    TariffSensorDescription(
        key="cheapest_window_start",
        translation_key="cheapest_window_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=_window("start"),
    ),
    TariffSensorDescription(
        key="cheapest_window_end",
        translation_key="cheapest_window_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=_window("end"),
    ),
    TariffSensorDescription(
        key="dearest_window_start",
        translation_key="dearest_window_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=_window("start", highest=True),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TariffConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(TariffSensor(coordinator, description) for description in SENSORS)
    if coordinator.accountant is not None:
        async_add_entities(BillSensor(coordinator, description) for description in BILL_SENSORS)
        if entry.options.get(CONF_HOUSE_ENERGY):
            async_add_entities([SavingsSensor(coordinator)])


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
        minutes = self.coordinator.config_entry.options.get(
            CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES
        )
        return self.entity_description.value(self.coordinator.data, dt_util.now(), minutes)
