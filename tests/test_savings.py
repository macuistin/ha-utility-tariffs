"""The saving this bill period, from the whole home's energy use and the battery."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from utility_tariffs_lib.tariff import SlotHistory

from custom_components.utility_tariffs.const import (
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_SOC,
    CONF_BATTERY_WEAR,
    CONF_HOUSE_ENERGY,
    CONF_IMPORT_ENERGY,
)
from custom_components.utility_tariffs.savings import battery_of, opening_charge
from tests.test_bill import METER, _minute, _set
from tests.test_sensor import NOON, _setup, _state

HOUSE = "sensor.house_energy"
SOC = "sensor.battery_charge"
SAVING = "sensor.utility_tariff_savings_this_bill_period"
DUBLIN = ZoneInfo("Europe/Dublin")


async def test_no_savings_sensor_without_a_house_meter(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, options={CONF_IMPORT_ENERGY: METER})

    assert hass.states.get(SAVING) is None


async def test_the_saving_is_the_grid_energy_the_system_avoided(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    _set(hass, METER, 100.0)
    _set(hass, HOUSE, 50.0)
    await _setup(hass, options={CONF_IMPORT_ENERGY: METER, CONF_HOUSE_ENERGY: HOUSE})
    assert hass.states.get(SAVING).state == "unknown"  # nothing recorded yet

    _set(hass, METER, 100.5)  # half a kWh from the grid ...
    _set(hass, HOUSE, 51.0)  # ... of one used, so half came from solar or the battery
    await _minute(hass, freezer)

    state = hass.states.get(SAVING)
    assert state is not None
    assert float(state.state) == pytest.approx(0.15)  # half a kWh at the day price
    assert state.attributes["bill_difference"] == pytest.approx(0.15)
    assert state.attributes["unit_of_measurement"] == "EUR"


async def test_a_battery_that_lost_charge_takes_its_value_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to("2026-11-14 12:29:30+00:00")
    _set(hass, METER, 100.0)
    _set(hass, HOUSE, 50.0)
    hass.states.async_set(SOC, "60", {"unit_of_measurement": "%"})
    options = {
        CONF_IMPORT_ENERGY: METER,
        CONF_HOUSE_ENERGY: HOUSE,
        CONF_BATTERY_SOC: SOC,
        CONF_BATTERY_CAPACITY: 10.0,
        CONF_BATTERY_WEAR: 0.0,
    }
    await _setup(hass, options=options)

    _set(hass, METER, 100.1)
    _set(hass, HOUSE, 50.1)
    hass.states.async_set(SOC, "50", {"unit_of_measurement": "%"})
    await _minute(hass, freezer)
    await _minute(hass, freezer)

    attributes = hass.states.get(SAVING).attributes
    # Ten percent of 10 kWh is gone, valued at the night price, the cheapest band.
    assert attributes["stored_energy_value"] == pytest.approx(-0.15)
    assert float(_state(hass, "savings_this_bill_period")) == pytest.approx(-0.15)


def test_the_opening_charge_is_the_last_reading_before_the_period() -> None:
    history = SlotHistory(DUBLIN)
    for day, percent in ((date(2026, 10, 28), 30.0), (date(2026, 10, 29), 45.0)):
        history.record_soc(datetime(day.year, day.month, day.day, 12, tzinfo=DUBLIN), percent)
    history.record_soc(datetime(2026, 11, 2, 12, tzinfo=DUBLIN), 80.0)

    assert opening_charge(history, date(2026, 11, 1), date(2026, 11, 3)) == 45.0


def test_with_no_reading_before_the_period_the_first_one_inside_it_is_used() -> None:
    history = SlotHistory(DUBLIN)
    history.record_soc(datetime(2026, 11, 2, 9, tzinfo=DUBLIN), 80.0)
    history.record_soc(datetime(2026, 11, 2, 15, tzinfo=DUBLIN), 60.0)

    assert opening_charge(history, date(2026, 11, 1), date(2026, 11, 3)) == 80.0
    assert opening_charge(SlotHistory(DUBLIN), date(2026, 11, 1), date(2026, 11, 3)) is None


def test_a_battery_needs_a_size() -> None:
    assert battery_of({}, 50.0) is None
    assert battery_of({CONF_BATTERY_CAPACITY: 10.0}, None) is not None
    battery = battery_of({CONF_BATTERY_CAPACITY: 10.0, CONF_BATTERY_WEAR: 0.02}, 50.0)
    assert battery is not None
    assert (battery.capacity_kwh, battery.soc_before_pct, battery.wear_per_kwh) == (
        10.0,
        50.0,
        0.02,
    )


async def test_the_options_flow_keeps_the_battery_settings(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "window_minutes": 120,
            CONF_IMPORT_ENERGY: METER,
            CONF_HOUSE_ENERGY: HOUSE,
            CONF_BATTERY_SOC: SOC,
            CONF_BATTERY_CAPACITY: 9.5,
            CONF_BATTERY_WEAR: 0.0,
        },
    )

    await hass.async_block_till_done()  # the reload the save schedules
    assert result["data"] == {
        "window_minutes": 120,
        CONF_IMPORT_ENERGY: METER,
        CONF_HOUSE_ENERGY: HOUSE,
        CONF_BATTERY_SOC: SOC,
        CONF_BATTERY_CAPACITY: 9.5,
        CONF_BATTERY_WEAR: 0.0,
    }
    assert await hass.config_entries.async_unload(entry.entry_id)
