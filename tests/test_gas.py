"""A gas entry: its own store, its own device, and no export prices."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from utility_tariffs_lib.tariffstore import AsyncMemoryCache, AsyncStore, folder_reader

from custom_components.utility_tariffs import coordinator, plan_steps
from custom_components.utility_tariffs.const import DOMAIN
from custom_components.utility_tariffs.energy_store import storage_key
from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess
from tests.helpers import async_reader
from tests.options_support import open_menu
from tests.support.building import build_store
from tests.support.fixtures import flat, write_store
from tests.test_sensor import DATA, NOON, _options, _setup, _sub

GAS = {**DATA, "service": "gas", "tariff": "flat", "area": "all", "name": "Gas Flat",
       "entity_key": "gas/IE/p/flat/all"}


@pytest.fixture
def stores(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    """An electricity store and a gas store at different prices. Lists the services asked for."""
    asked: list[str] = []
    accesses = {}
    for service, price in (("electricity", "0.25"), ("gas", "0.07")):
        # A gas tariff file says so, and the library only accepts that from the release that added gas.
        extra = {"service": "gas"} if service == "gas" else {}
        folder = write_store(tmp_path / service, {"p/flat/1.json": flat(price, **extra)})
        build_store(folder)
        store = AsyncStore(async_reader(folder_reader(folder)), AsyncMemoryCache())
        accesses[service] = TariffStoreAccess(hass, store)

    def access(_hass: HomeAssistant, service: str = "electricity") -> TariffStoreAccess:
        asked.append(service)
        return accesses[service]

    monkeypatch.setattr(plan_steps, "store_access", access)
    monkeypatch.setattr(coordinator, "store_access", access)
    return asked


async def test_a_gas_entry_reads_the_gas_store_on_its_own_device(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, GAS)

    assert "gas" in stores
    state = hass.states.get("sensor.gas_tariff_gas_price")
    assert state is not None
    assert state.state == "0.07"
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [(d.identifiers, d.name) for d in devices] == [
        ({(DOMAIN, "gas/IE/p/flat/all")}, "Gas tariff")
    ]
    assert _sub(entry, "gas").data["service"] == "gas"


async def test_a_gas_entry_has_no_export_sensors(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, GAS)

    ids = [e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)]
    assert ids
    assert not [unique for unique in ids if "_export_" in unique or "export_price" in unique]


async def test_electricity_and_gas_entries_sit_side_by_side(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, {**DATA, "tariff": "flat", "area": "all", "name": "Elec Flat"})
    await _setup(hass, {**GAS, "name": "Gas Flat"})

    power = hass.states.get("sensor.electricity_tariff_import_price")
    gas = hass.states.get("sensor.gas_tariff_gas_price")
    assert power is not None
    assert gas is not None
    assert (power.state, gas.state) == ("0.25", "0.07")


async def test_gas_entities_are_named_gas_and_electricity_keeps_its_names(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, {**DATA, "tariff": "flat", "area": "all", "name": "Elec Flat"})
    await _setup(hass, GAS)

    registry = er.async_get(hass)
    ids = [e.entity_id for e in registry.entities.values() if e.platform == DOMAIN]
    gas = [i for i in ids if i.startswith("sensor.gas_tariff_") or i.startswith("binary_sensor.gas_tariff_")]
    assert gas
    assert not [i for i in gas if "import" in i or "electricity" in i or "battery" in i]
    assert "sensor.electricity_tariff_import_price" in ids
    assert not [i for i in ids if i.startswith("sensor.electricity_tariff_gas")]


async def test_each_service_has_its_own_device_and_no_entity_is_on_both(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]
) -> None:
    freezer.move_to(NOON)
    power = await _setup(hass, {**DATA, "tariff": "flat", "area": "all", "name": "Elec Flat"})
    gas = await _setup(hass, GAS)

    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    assert power is gas  # one entry holds both tariffs
    seen: dict[str, set[str | None]] = {}
    for entity in er.async_entries_for_config_entry(registry, power.entry_id):
        seen.setdefault(entity.config_subentry_id or "", set()).add(entity.device_id)
    elec, gas_id = _sub(power, "electricity").subentry_id, _sub(power, "gas").subentry_id
    assert seen[elec].isdisjoint(seen[gas_id])
    assert {devices.async_get(d).name for d in seen[elec]} == {"Electricity tariff"}  # type: ignore[union-attr]
    assert {devices.async_get(d).name for d in seen[gas_id]} == {"Gas tariff"}  # type: ignore[union-attr]
    assert all(d.via_device_id is None for d in dr.async_entries_for_config_entry(devices, power.entry_id))
    assert {sub.title for sub in power.subentries.values()} == {"Electricity tariff", "Gas tariff"}


async def test_the_gas_options_ask_only_for_gas_things(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, GAS)

    menu = await open_menu(hass, entry.entry_id)

    assert menu["menu_options"] == [
        "tariff_electricity", "tariff_gas", "meters_gas", "store", "done"
    ]  # no electricity meters or battery: only gas is followed
    page = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "meters_gas"}
    )
    fields = {str(key) for key in page["data_schema"].schema}
    assert fields == {"import_energy_entity", "history_start", "backfill_now"}
    page = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"import_energy_entity": "sensor.gas_kwh"}
    )
    for step in ("tariff_gas", "bills"):
        page = await hass.config_entries.options.async_configure(
            page["flow_id"], {"next_step_id": step}
        )
    assert "connected_load_kw" not in {str(key) for key in page["data_schema"].schema}
    page = await hass.config_entries.options.async_configure(page["flow_id"], {})
    saved = await hass.config_entries.options.async_configure(
        page["flow_id"], {"next_step_id": "done"}
    )
    assert saved["type"] == "create_entry"
    assert _options(entry, "gas")["import_energy_entity"] == "sensor.gas_kwh"
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_removing_the_gas_tariff_removes_its_device_and_saved_history(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str],
    hass_storage: dict[str, Any],
) -> None:
    freezer.move_to(NOON)
    hass.states.async_set("sensor.gas_kwh", "100", {"unit_of_measurement": "kWh"})
    power = await _setup(hass, {**DATA, "tariff": "flat", "area": "all", "name": "Elec Flat"})
    await _setup(hass, {**GAS, "import_energy_entity": "sensor.gas_kwh"})
    key = storage_key(_sub(power, "gas").subentry_id)
    gas_device = next(
        d.id for d in dr.async_entries_for_config_entry(dr.async_get(hass), power.entry_id)
        if d.name == "Gas tariff"
    )

    hass.config_entries.async_remove_subentry(power, _sub(power, "gas").subentry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.gas_tariff_gas_price") is None
    assert hass.states.get("sensor.electricity_tariff_import_price") is not None
    assert dr.async_get(hass).async_get(gas_device) is None
    assert key not in hass_storage


async def test_an_action_names_the_fuel_it_uses(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]
) -> None:
    freezer.move_to(NOON)
    power = await _setup(hass, {**DATA, "tariff": "flat", "area": "all", "name": "Elec Flat"})
    await _setup(hass, GAS)
    call = {"config_entry_id": power.entry_id, "start": NOON, "end": "2026-11-14 13:00:00+00:00"}

    elec = await hass.services.async_call(
        DOMAIN, "get_prices", call, blocking=True, return_response=True
    )
    gas = await hass.services.async_call(
        DOMAIN, "get_prices", {**call, "service": "gas"}, blocking=True, return_response=True
    )

    assert elec["prices"][0]["import_price"] == 0.25
    assert gas["prices"][0]["import_price"] == 0.07
