"""A gas entry: its own store, its own device, and no export prices."""

from __future__ import annotations

from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from utility_tariffs_lib.tariffstore import AsyncMemoryCache, AsyncStore, folder_reader

from custom_components.utility_tariffs import config_flow, coordinator
from custom_components.utility_tariffs.const import DOMAIN
from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess
from tests.helpers import async_reader
from tests.support.building import build_store
from tests.support.fixtures import flat, write_store
from tests.test_sensor import DATA, NOON, _setup

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

    monkeypatch.setattr(config_flow, "store_access", access)
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
        ({(DOMAIN, "gas/IE/p/flat/all")}, "Gas Tariff")
    ]
    assert entry.data["service"] == "gas"


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

    power = hass.states.get("sensor.utility_tariff_import_price")
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
    assert "sensor.utility_tariff_import_price" in ids
    assert not [i for i in ids if i.startswith("sensor.utility_tariff_gas")]


async def test_each_service_has_its_own_device_and_no_entity_is_on_both(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]
) -> None:
    freezer.move_to(NOON)
    power = await _setup(hass, {**DATA, "tariff": "flat", "area": "all", "name": "Elec Flat"})
    gas = await _setup(hass, GAS)

    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    seen: dict[str, set[str | None]] = {}
    for entry in (power, gas):
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            seen.setdefault(entry.entry_id, set()).add(entity.device_id)
    assert seen[power.entry_id].isdisjoint(seen[gas.entry_id])
    assert {devices.async_get(d).name for d in seen[power.entry_id]} == {"Utility Tariff"}  # type: ignore[union-attr]
    assert {devices.async_get(d).name for d in seen[gas.entry_id]} == {"Gas Tariff"}  # type: ignore[union-attr]


async def test_the_gas_options_ask_only_for_gas_things(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, GAS)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["step_id"] == "init_gas"
    fields = {str(key) for key in result["data_schema"].schema}
    assert {"import_energy_entity", "bill_start_day", "window_minutes"} <= fields
    assert not fields & {
        "export_energy_entity",
        "house_energy_entity",
        "battery_discharge_energy_entity",
        "battery_soc_entity",
        "battery_capacity_kwh",
        "battery_wear_per_kwh",
        "connected_load_kw",
    }
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"], {"window_minutes": 60, "import_energy_entity": "sensor.gas_kwh"}
    )
    assert saved["data"]["import_energy_entity"] == "sensor.gas_kwh"
