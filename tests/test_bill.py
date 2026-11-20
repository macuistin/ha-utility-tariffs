"""The bill so far, priced from the energy the user's own meters count."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.utility_tariffs.const import (
    CONF_EXPORT_ENERGY,
    CONF_IMPORT_ENERGY,
    CONF_MAX_METER_KW,
    DOMAIN,
)
from custom_components.utility_tariffs.diagnostics import async_get_config_entry_diagnostics
from custom_components.utility_tariffs.energy_store import storage_key
from tests.test_sensor import NOON, _setup, _state

METER = "sensor.meter_in"
EXPORT_METER = "sensor.meter_out"


def _set(hass: HomeAssistant, entity_id: str, value: float, unit: str = "kWh") -> None:
    hass.states.async_set(entity_id, str(value), {"unit_of_measurement": unit})


async def _minute(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def _setup_with_meters(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOON)
    _set(hass, METER, 100.0)
    _set(hass, EXPORT_METER, 20.0)
    entry = await _setup(
        hass, options={CONF_IMPORT_ENERGY: METER, CONF_EXPORT_ENERGY: EXPORT_METER}
    )
    assert entry.options[CONF_IMPORT_ENERGY] == METER


async def test_no_bill_sensors_without_a_meter(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert hass.states.get("sensor.utility_tariff_bill_so_far") is None


async def test_the_import_the_meter_counts_is_priced_into_the_bill(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _setup_with_meters(hass, freezer)
    before = float(_state(hass, "bill_so_far"))

    _set(hass, METER, 101.0)
    await _minute(hass, freezer)

    assert float(_state(hass, "import_this_bill_period")) == 1.0
    assert float(_state(hass, "bill_so_far")) > before


async def test_a_meter_in_watt_hours_is_converted(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    _set(hass, METER, 100000.0, "Wh")
    await _setup(hass, options={CONF_IMPORT_ENERGY: METER})

    _set(hass, METER, 100500.0, "Wh")
    await _minute(hass, freezer)

    assert float(_state(hass, "import_this_bill_period")) == 0.5


async def test_export_is_credited(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _setup_with_meters(hass, freezer)
    before = float(_state(hass, "bill_so_far"))

    _set(hass, EXPORT_METER, 22.0)
    await _minute(hass, freezer)

    assert float(_state(hass, "bill_so_far")) <= before


async def test_the_unit_and_period_are_on_the_bill(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _setup_with_meters(hass, freezer)

    state = hass.states.get("sensor.utility_tariff_bill_so_far")

    assert state is not None
    assert state.attributes["unit_of_measurement"] == "EUR"
    assert state.attributes["period_start"] <= "2026-11-14" < state.attributes["next_period_start"]


async def test_the_options_flow_saves_and_clears_the_meters(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"window_minutes": 120, CONF_IMPORT_ENERGY: METER, CONF_EXPORT_ENERGY: EXPORT_METER},
    )
    await hass.async_block_till_done()  # the reload the save schedules
    assert result["data"] == {
        "window_minutes": 120,
        CONF_IMPORT_ENERGY: METER,
        CONF_EXPORT_ENERGY: EXPORT_METER,
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"window_minutes": 120}
    )
    assert result["data"] == {"window_minutes": 120}
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_the_history_survives_a_restart_and_goes_with_the_plan(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    use_store: Callable[..., Path],
    hass_storage: dict[str, Any],
) -> None:
    await _setup_with_meters(hass, freezer)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    _set(hass, METER, 101.0)
    await _minute(hass, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    key = storage_key(entry.entry_id)
    assert hass_storage[key]["data"]["days"]

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert float(_state(hass, "import_this_bill_period")) == 1.0

    await hass.config_entries.async_remove(entry.entry_id)
    assert key not in hass_storage


@pytest.mark.parametrize("days", [["not a day", 7], 5])
async def test_an_unreadable_saved_history_starts_fresh(
    days: object,
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    use_store: Callable[..., Path],
    hass_storage: dict[str, Any],
) -> None:
    freezer.move_to(NOON)
    hass_storage[storage_key("fixed")] = {
        "version": 1,
        "key": storage_key("fixed"),
        "data": {"days": days},
    }
    _set(hass, METER, 1.0)
    await _setup(hass, options={CONF_IMPORT_ENERGY: METER}, entry_id="fixed")

    assert float(_state(hass, "import_this_bill_period")) == 0.0


async def test_the_bill_dates_the_user_sets_replace_the_tariffs(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)  # 14 November
    _set(hass, METER, 100.0)
    await _setup(
        hass,
        options={
            CONF_IMPORT_ENERGY: METER,
            "bill_start_day": 10,
            "bill_months": 2,
            "bill_start_month": 1,
        },
    )

    attributes = hass.states.get("sensor.utility_tariff_bill_so_far").attributes
    assert attributes["period_start"] == "2026-11-10"
    assert attributes["next_period_start"] == "2027-01-10"
    assert attributes["days_in_period"] == 61


async def test_without_set_dates_the_tariffs_own_apply(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    _set(hass, METER, 100.0)
    await _setup(hass, options={CONF_IMPORT_ENERGY: METER})

    attributes = hass.states.get("sensor.utility_tariff_bill_so_far").attributes
    assert attributes["period_start"] == "2026-11-01"
    assert attributes["next_period_start"] == "2026-12-01"


async def test_a_jump_no_supply_could_deliver_is_not_billed_and_is_reported(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _setup_with_meters(hass, freezer)
    before = float(_state(hass, "bill_so_far"))

    _set(hass, METER, 5000.0)
    await _minute(hass, freezer)

    assert float(_state(hass, "import_this_bill_period")) == 0.0
    assert float(_state(hass, "bill_so_far")) == before
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "meter_readings_left_out")
    assert issue is not None
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["meter"] == METER


async def test_the_repair_clears_a_day_after_the_last_bad_reading(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _setup_with_meters(hass, freezer)
    _set(hass, METER, 5000.0)
    await _minute(hass, freezer)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "meter_readings_left_out") is not None

    freezer.tick(timedelta(hours=25))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, "meter_readings_left_out") is None


async def test_a_negative_reading_is_not_booked_as_use(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _setup_with_meters(hass, freezer)

    _set(hass, METER, -3.0)
    await _minute(hass, freezer)
    _set(hass, METER, 100.4)
    await _minute(hass, freezer)

    assert float(_state(hass, "import_this_bill_period")) == 0.0


async def test_a_reset_is_not_booked_and_raises_no_repair(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _setup_with_meters(hass, freezer)

    _set(hass, METER, 2.0)
    await _minute(hass, freezer)
    _set(hass, METER, 2.5)
    await _minute(hass, freezer)

    assert float(_state(hass, "import_this_bill_period")) == 0.5
    assert ir.async_get(hass).async_get_issue(DOMAIN, "meter_readings_left_out") is None


async def test_the_limit_in_the_options_decides_what_is_too_large(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    _set(hass, METER, 100.0)
    await _setup(hass, options={CONF_IMPORT_ENERGY: METER, CONF_MAX_METER_KW: 6.0})

    _set(hass, METER, 100.2)  # 12 kW for the minute
    await _minute(hass, freezer)

    assert float(_state(hass, "import_this_bill_period")) == 0.0


async def test_diagnostics_list_what_was_left_out(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _setup_with_meters(hass, freezer)
    _set(hass, METER, 5000.0)
    await _minute(hass, freezer)
    [entry] = hass.config_entries.async_entries(DOMAIN)

    report = await async_get_config_entry_diagnostics(hass, entry)

    [row] = report["coordinator"]["meter_readings_left_out"]
    assert (row["meter"], row["reason"], row["kwh"]) == (CONF_IMPORT_ENERGY, "too_large", 4900.0)
    assert METER not in str(report)
