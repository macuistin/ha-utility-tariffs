"""Sensors for the bill so far, from the energy the user's own meters counted."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.util import dt as dt_util
from utility_tariffs_lib.tariff import PeriodBill

from .bill import bill_so_far
from .bill_lines import paid_lines, projected_total
from .coordinator import TariffCoordinator
from .entity import TariffEntity


@dataclass(frozen=True, kw_only=True)
class BillSensorDescription(SensorEntityDescription):
    """A figure of the bill so far."""

    value: Callable[[PeriodBill], float]
    money: bool = False  # the unit is the tariff's currency


def _import_kwh(bill: PeriodBill) -> float:
    return float(sum(bill.import_kwh_by_band.values()))


BILL_SENSORS = (
    BillSensorDescription(
        key="bill_so_far",
        translation_key="bill_so_far",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        money=True,
        value=lambda bill: float(bill.priced.total),
    ),
    BillSensorDescription(
        key="period_import",
        translation_key="period_import",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value=_import_kwh,
    ),
    BillSensorDescription(
        key="bill_coverage",
        translation_key="bill_coverage",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value=lambda bill: bill.coverage * 100,
    ),
)


class BillSensor(TariffEntity, SensorEntity):
    """One figure of the bill so far in the current bill period."""

    entity_description: BillSensorDescription
    # The lines change every minute and are not worth keeping in the history.
    _unrecorded_attributes = frozenset({"lines"})

    def __init__(self, coordinator: TariffCoordinator, description: BillSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.money:
            self._attr_native_unit_of_measurement = coordinator.data.definition.currency

    def _bill(self) -> PeriodBill | None:
        accountant = self.coordinator.accountant
        if accountant is None:
            return None
        return bill_so_far(
            accountant.store.history,
            self.coordinator.data,
            self.coordinator.fuel.options,
            dt_util.now(),
        )

    @property
    def native_value(self) -> float | None:
        bill = self._bill()
        return None if bill is None else self.entity_description.value(bill)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        bill = self._bill()
        if bill is None or self.entity_description.key != "bill_so_far":
            return None
        return {
            "period_start": bill.first_day.isoformat(),
            "next_period_start": bill.next_first_day.isoformat(),
            "days_priced": bill.days,
            "days_in_period": bill.period_days,
            "days_left": bill.period_days - bill.days,
            "projected_bill": self._projection(bill),
            "lines": paid_lines(bill),
        }

    def _projection(self, bill: PeriodBill) -> float | None:
        accountant = self.coordinator.accountant
        if accountant is None:
            return None
        return projected_total(
            accountant.store.history, self.coordinator.data, self.coordinator.fuel.options, bill
        )
