"""The form fields for the energy meters, the bill dates and the battery, shared by the pages."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers.selector import (
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    BILL_MONTHS,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_DISCHARGE_ENERGY,
    CONF_BATTERY_SOC,
    CONF_BATTERY_WEAR,
    CONF_BILL_MONTHS,
    CONF_BILL_START_DAY,
    CONF_BILL_START_MONTH,
    CONF_CONNECTED_LOAD,
    CONF_EXPORT_ENERGY,
    CONF_HISTORY_START,
    CONF_HOUSE_ENERGY,
    CONF_IMPORT_ENERGY,
    CONF_MAX_METER_KW,
    MAX_BILL_START_DAY,
)

_METERS = (CONF_IMPORT_ENERGY, CONF_EXPORT_ENERGY, CONF_HOUSE_ENERGY, CONF_BATTERY_DISCHARGE_ENERGY)
_NUMBERS = {
    CONF_BATTERY_CAPACITY: "kWh",
    CONF_BATTERY_WEAR: None,
    CONF_CONNECTED_LOAD: "kW",
    CONF_MAX_METER_KW: "kW",
}


def _gas_meter_fields(options: Any) -> dict[Any, Any]:
    """Gas has one meter, what the home used, and no battery."""
    meter = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="energy"))
    return {
        vol.Optional(
            CONF_IMPORT_ENERGY, description={"suggested_value": options.get(CONF_IMPORT_ENERGY)}
        ): meter,
        vol.Optional(
            CONF_HISTORY_START, description={"suggested_value": options.get(CONF_HISTORY_START)}
        ): DateSelector(),
    }


def _meter_fields(options: Any) -> dict[Any, Any]:
    """The energy meters and the battery charge, each with its current value suggested."""
    meter = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="energy"))
    charge = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="battery"))
    fields: dict[Any, Any] = {
        vol.Optional(key, description={"suggested_value": options.get(key)}): meter
        for key in _METERS
    }
    fields[
        vol.Optional(
            CONF_HISTORY_START, description={"suggested_value": options.get(CONF_HISTORY_START)}
        )
    ] = DateSelector()
    fields[
        vol.Optional(
            CONF_BATTERY_SOC, description={"suggested_value": options.get(CONF_BATTERY_SOC)}
        )
    ] = charge
    return fields


def _bill_fields(options: Any) -> dict[Any, Any]:
    """Where a bill starts and how long it runs. Left empty, the tariff's own dates apply."""
    day = NumberSelectorConfig(
        min=1, max=MAX_BILL_START_DAY, step=1, mode=NumberSelectorMode.BOX
    )
    month = NumberSelectorConfig(min=1, max=12, step=1, mode=NumberSelectorMode.BOX)
    lengths = [SelectOptionDict(value=str(n), label=str(n)) for n in BILL_MONTHS]
    suggested = options.get(CONF_BILL_MONTHS)
    return {
        vol.Optional(
            CONF_BILL_START_DAY, description={"suggested_value": options.get(CONF_BILL_START_DAY)}
        ): NumberSelector(day),
        vol.Optional(
            CONF_BILL_MONTHS,
            description={"suggested_value": None if suggested is None else str(suggested)},
        ): SelectSelector(SelectSelectorConfig(options=lengths)),
        vol.Optional(
            CONF_BILL_START_MONTH,
            description={"suggested_value": options.get(CONF_BILL_START_MONTH)},
        ): NumberSelector(month),
    }


def _saved_setup(user_input: dict[str, Any]) -> dict[str, Any]:
    """The meters, battery charge and bill dates that were filled in."""
    data: dict[str, Any] = {}
    meters = (*_METERS, CONF_BATTERY_SOC, CONF_HISTORY_START)
    data.update({k: user_input[k] for k in meters if user_input.get(k)})
    bills = (CONF_BILL_START_DAY, CONF_BILL_MONTHS, CONF_BILL_START_MONTH)
    data.update({k: int(user_input[k]) for k in bills if user_input.get(k)})
    return data
