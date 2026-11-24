"""Configure: pages that change nothing until Save changes, the tariff change and the second fuel."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.utility_tariffs.const import DOMAIN
from tests.helpers import without_bands
from tests.options_support import configure, fill_windows, open_menu
from tests.test_gas import stores  # noqa: F401  the electricity and gas stores
from tests.test_sensor import DATA, NOON, _setup

FLAT = "P Energy – Flat"
FLAT_DATA = {**DATA, "tariff": "flat", "area": "all", "name": "P Energy Flat"}


async def _choose_plan(
    hass: HomeAssistant, flow_id: str, plan: str = FLAT, service: str = "electricity"
) -> dict:
    flow = hass.config_entries.options
    await flow.async_configure(flow_id, {"next_step_id": f"tariff_{service}"})
    result = await flow.async_configure(flow_id, {"next_step_id": "country"})
    assert result["step_id"] == "country"
    result = await flow.async_configure(flow_id, {"country": "IE"})
    return await flow.async_configure(flow_id, {"tariff": plan})


async def test_the_menu_says_what_each_page_holds_now(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, options={"import_energy_entity": "sensor.grid_in"})

    menu = await open_menu(hass, entry.entry_id)

    assert menu["menu_options"] == [
        "tariff_electricity", "tariff_gas", "meters", "battery", "store"
    ]
    lines = menu["description_placeholders"]
    assert lines["electricity_summary"] == "P Energy Plan (Urban) (IE)"
    assert lines["gas_summary"] == "not followed yet, choose a gas plan"
    assert lines["meters_summary"] == "import sensor.grid_in"
    assert lines["battery_summary"] == "no battery set"
    assert lines["unsaved"] == ""
    hass.config_entries.options.async_abort(menu["flow_id"])
    await hass.config_entries.async_unload(entry.entry_id)


async def test_nothing_is_saved_until_save_changes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)
    menu = await open_menu(hass, entry.entry_id)

    menu = await fill_windows(hass, menu["flow_id"], "electricity", {"window_minutes": 240})

    assert entry.options == {}
    assert "confirm" in menu["menu_options"]
    assert menu["description_placeholders"]["unsaved"].startswith("You have unsaved changes")
    result = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "confirm"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"window_minutes": 240}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_field_emptied_on_its_page_is_removed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, options={"import_energy_entity": "sensor.grid_in"})

    result = await configure(hass, entry.entry_id, meters={})
    await hass.async_block_till_done()

    assert result["data"] == {}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_the_tariff_changes_in_configure_and_keeps_the_entities(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)
    registry = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    menu = await open_menu(hass, entry.entry_id)

    page = await _choose_plan(hass, menu["flow_id"])
    assert page["step_id"] == "plan_bills"  # the bill dates are asked before the plan is saved
    assert "connected_load_kw" in {str(key) for key in page["data_schema"].schema}
    menu = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"bill_start_day": 16, "bill_months": "2"}
    )

    assert menu["step_id"] == "init"
    assert menu["description_placeholders"]["electricity_summary"] == (
        "changes to P Energy Flat when you save, bill starts on day 16, 2 months a bill"
    )
    assert entry.data["tariff"] == "plan"  # not saved yet
    result = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "confirm"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data["tariff"] == "flat"
    assert entry.options == {"bill_start_day": 16, "bill_months": 2}
    assert entry.title == "P Energy Flat"
    assert entry.unique_id == "IE/p/flat/all"
    after = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert without_bands(after) == without_bands(before)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_the_own_rates_pages_work_from_configure(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)
    menu = await open_menu(hass, entry.entry_id)
    flow, flow_id = hass.config_entries.options, menu["flow_id"]

    result = await _choose_plan(hass, flow_id, "Type in my own rates")
    assert result["step_id"] == "manual_template"
    result = await flow.async_configure(flow_id, {"template": "blank"})
    result = await flow.async_configure(
        flow_id,
        {
            "name": "Mine", "country": "IE", "currency": "EUR", "base_rate_name": "Day",
            "base_rate": 0.3, "export_rate": 0.1, "standing_charge": 0.5, "levy": 0,
            "discount_rate": 0, "vat_rate": 9, "vat_included": False, "bill_start_day": 1,
        },
    )
    assert result["step_id"] == "manual_more"
    page = await flow.async_configure(flow_id, {"next_step_id": "manual_done"})
    assert page["step_id"] == "plan_bills"
    menu = await flow.async_configure(flow_id, {})
    assert menu["step_id"] == "init"
    result = await flow.async_configure(flow_id, {"next_step_id": "confirm"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data["manual"]["base_rate"] == 0.3
    assert entry.title == "Mine"
    assert entry.data["entity_key"] == "IE/p/plan/urban"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_plan_another_entry_follows_is_refused(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    MockConfigEntry(domain=DOMAIN, unique_id="IE/p/flat/all", data={}).add_to_hass(hass)
    entry = await _setup(hass)
    menu = await open_menu(hass, entry.entry_id)

    result = await _choose_plan(hass, menu["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_gas_is_added_from_configure_and_made_when_saved(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]  # noqa: F811
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, FLAT_DATA)
    menu = await open_menu(hass, entry.entry_id)
    flow, flow_id = hass.config_entries.options, menu["flow_id"]

    result = await flow.async_configure(flow_id, {"next_step_id": "tariff_gas"})
    assert result["step_id"] == "country"
    result = await flow.async_configure(flow_id, {"country": "IE"})
    result = await flow.async_configure(flow_id, {"tariff": FLAT})
    assert result["step_id"] == "new_options_gas"
    menu = await flow.async_configure(flow_id, {"import_energy_entity": "sensor.gas_kwh"})

    assert menu["step_id"] == "init"
    assert menu["description_placeholders"]["gas_summary"] == "P Energy Flat is added when you save"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    await flow.async_configure(flow_id, {"next_step_id": "confirm"})
    await hass.async_block_till_done()

    gas = [e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("service") == "gas"]
    assert len(gas) == 1
    assert gas[0].options == {"import_energy_entity": "sensor.gas_kwh"}
    assert hass.states.get("sensor.gas_tariff_gas_price") is not None
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.config_entries.async_unload(gas[0].entry_id)


async def test_the_other_fuel_is_changed_from_the_same_menu_with_its_bill_dates(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]  # noqa: F811
) -> None:
    from tests.test_gas import GAS

    freezer.move_to(NOON)
    power = await _setup(hass, FLAT_DATA)
    gas = await _setup(hass, GAS)
    menu = await open_menu(hass, power.entry_id)
    assert menu["description_placeholders"]["gas_summary"] == "Gas Flat (IE)"

    page = await _choose_plan(hass, menu["flow_id"], FLAT, service="gas")
    assert page["step_id"] == "plan_bills"
    assert "connected_load_kw" not in {str(key) for key in page["data_schema"].schema}
    menu = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"bill_start_day": 5}
    )

    assert power.options == {} and gas.options == {}  # nothing saved yet
    await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "confirm"}
    )
    await hass.async_block_till_done()
    assert gas.unique_id == "gas/IE/p/flat/all"  # moved to the store's own gas plan id
    assert gas.data["service"] == "gas"
    assert gas.options == {"bill_start_day": 5}
    assert power.options == {}
    await hass.config_entries.async_unload(power.entry_id)
    await hass.config_entries.async_unload(gas.entry_id)


async def test_the_window_settings_are_on_the_tariff_page_of_each_fuel(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]  # noqa: F811
) -> None:
    from tests.test_gas import GAS

    freezer.move_to(NOON)
    power = await _setup(hass, FLAT_DATA)
    gas = await _setup(hass, GAS)
    menu = await open_menu(hass, power.entry_id)
    flow = hass.config_entries.options
    page = await flow.async_configure(menu["flow_id"], {"next_step_id": "tariff_gas"})
    assert "windows" in page["menu_options"]
    assert page["description_placeholders"]["windows_summary"].startswith("120 minute")
    await flow.async_configure(menu["flow_id"], {"next_step_id": "init"})

    await fill_windows(hass, menu["flow_id"], "gas", {"window_minutes": 60})
    await flow.async_configure(menu["flow_id"], {"next_step_id": "confirm"})
    await hass.async_block_till_done()

    assert gas.options == {"window_minutes": 60}
    assert power.options == {}
    await hass.config_entries.async_unload(power.entry_id)
    await hass.config_entries.async_unload(gas.entry_id)
