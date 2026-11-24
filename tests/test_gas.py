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
        folder = write_store(tmp_path / service, {"p/flat/1.json": flat(price)})
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
    state = hass.states.get("sensor.gas_tariff_import_price")
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
    gas = hass.states.get("sensor.gas_tariff_import_price")
    assert power is not None
    assert gas is not None
    assert (power.state, gas.state) == ("0.25", "0.07")
