"""The saving from solar and a battery this bill period."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.util import dt as dt_util
from utility_tariffs_lib.tariff import DefinitionSavings

from .coordinator import TariffCoordinator
from .entity import TariffEntity
from .savings import saving_so_far


class _SavingsEntity(TariffEntity, SensorEntity):
    """A figure worked out from the saving this bill period."""

    def _saving(self) -> DefinitionSavings | None:
        accountant = self.coordinator.accountant
        if accountant is None:
            return None
        return saving_so_far(
            accountant.store.history,
            self.coordinator.data,
            self.coordinator.fuel.options,
            dt_util.now(),
        )



class SavingsSensor(_SavingsEntity):
    """What the home saved this bill period against buying all of its energy from the grid."""

    _attr_translation_key = "savings_this_period"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "savings_this_period")
        self._attr_native_unit_of_measurement = coordinator.data.definition.currency

    @property
    def native_value(self) -> float | None:
        saving = self._saving()
        return None if saving is None else float(saving.total)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        saving = self._saving()
        if saving is None:
            return None
        return {
            "bill_without_system": float(saving.without_system.priced.total),
            "bill_so_far": float(saving.actual.priced.total),
            "bill_difference": float(saving.bill_difference),
            "stored_energy_value": float(saving.stored_energy_value),
            "battery_wear": float(saving.battery_wear),
            "coverage": round(saving.coverage, 3),
        }


class SavingsShareSensor(_SavingsEntity):
    """The saving as a share of what the bill would have been without it."""

    _attr_translation_key = "savings_share_this_period"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "savings_share_this_period")

    @property
    def native_value(self) -> float | None:
        saving = self._saving()
        if saving is None:
            return None
        without = saving.without_system.priced.total
        return round(float(100 * saving.total / without), 1) if without > 0 else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        saving = self._saving()
        if saving is None:
            return None
        return {
            "days_covered": saving.actual.days_recorded,
            "days_in_period": saving.actual.period_days,
            "coverage": round(saving.coverage, 3),
        }
