"""A tariff that charges per kW of connected load needs the household's load from the options."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from utility_tariffs_lib.tariffstore import AsyncFolderCache, AsyncStore, folder_reader

from custom_components.utility_tariffs import config_flow, coordinator
from custom_components.utility_tariffs.bill_period import period_rules
from custom_components.utility_tariffs.const import (
    CONF_CONNECTED_LOAD,
    CONF_IMPORT_ENERGY,
    LOAD_NAME,
)
from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess
from tests.helpers import async_reader
from tests.support.building import build_store
from tests.support.fixtures import flat, write_store
from tests.test_sensor import NOON, _setup, _state

METER = "sensor.meter_in"
DATA = {
    "country": "IE",
    "provider": "p",
    "tariff": "load",
    "area": "all",
    "name": "P Energy Load",
}
# 10 a month for every kW of the sanctioned load, whatever the band, and no energy price.
LOAD_BILL = {
    "total": {
        "kind": "sum",
        "of": {
            "fixed": {
                "kind": "connected_load",
                "load": LOAD_NAME,
                "bands": {"all": {"price": "10"}},
            }
        },
    }
}


@pytest.fixture
def load_store(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """A built store whose one plan has a connected load charge."""
    folder = write_store(tmp_path, {"p/load/1.json": flat(bill=LOAD_BILL)})
    build_store(folder)
    store = AsyncStore(async_reader(folder_reader(folder)), AsyncFolderCache(tmp_path / "cache"))
    access = TariffStoreAccess(hass, store, tmp_path / "cache")
    monkeypatch.setattr(config_flow, "store_access", lambda _hass: access)
    monkeypatch.setattr(coordinator, "store_access", lambda _hass: access)
    return folder


def test_a_set_load_becomes_the_rule_under_the_name_the_store_uses() -> None:
    rules = period_rules({CONF_CONNECTED_LOAD: 5.5}, lambda _day: False)

    assert rules.load_kw == {LOAD_NAME: Decimal("5.5")}


def test_no_load_set_leaves_the_rule_empty() -> None:
    assert period_rules({}, lambda _day: False).load_kw == {}


async def test_the_bill_charges_per_kw_of_the_load_set(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, load_store: Path
) -> None:
    freezer.move_to(NOON)
    hass.states.async_set(METER, "100", {"unit_of_measurement": "kWh"})

    await _setup(hass, data=DATA, options={CONF_IMPORT_ENERGY: METER, CONF_CONNECTED_LOAD: 5})

    assert float(_state(hass, "bill_so_far")) == 50.0  # 5 kW x 10 for the month


async def test_there_is_no_bill_until_the_load_is_set(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, load_store: Path
) -> None:
    freezer.move_to(NOON)
    hass.states.async_set(METER, "100", {"unit_of_measurement": "kWh"})

    await _setup(hass, data=DATA, options={CONF_IMPORT_ENERGY: METER})

    assert _state(hass, "bill_so_far") == "unknown"


async def test_the_options_keep_the_connected_load(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, load_store: Path
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, data=DATA)

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"window_minutes": 120, CONF_CONNECTED_LOAD: 4.5}
    )

    assert flow["type"] is FlowResultType.CREATE_ENTRY
    assert flow["data"][CONF_CONNECTED_LOAD] == 4.5
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)

