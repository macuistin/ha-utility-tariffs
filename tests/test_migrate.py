"""Entries from before one entry held both fuels move over with nothing lost."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.utility_tariffs.const import DOMAIN, hub_identifier
from custom_components.utility_tariffs.energy_store import storage_key
from tests.test_gas import GAS, stores  # noqa: F401  the electricity and gas stores
from tests.test_sensor import DATA, NOON, _coordinator

POWER = {**DATA, "tariff": "flat", "area": "all", "name": "Elec Flat"}
METER = "sensor.grid_in"


def _old_entry(data: dict[str, str], options: dict[str, Any], unique: str, entry_id: str) -> Any:
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, unique_id=unique, data=data, options=options,
        title=data["name"], entry_id=entry_id,
    )
    return entry


def _register(hass: HomeAssistant, entry: MockConfigEntry, key: str, name: str, unique: str) -> str:
    """What an earlier version left in the registries for this entry: a device and an entity."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, key)}, name=name
    )
    return er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{key}_{unique}", config_entry=entry, device_id=device.id,
        suggested_object_id=f"{name.lower().replace(' ', '_')}_{unique}",
    ).entity_id


async def test_two_entries_become_one_with_a_subentry_each(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str],  # noqa: F811
    hass_storage: dict[str, Any],
) -> None:
    freezer.move_to(NOON)
    await hass.config.async_set_time_zone("Europe/Dublin")
    power = _old_entry(POWER, {"import_energy_entity": METER}, "IE/p/flat/all", "power-id")
    gas = _old_entry(GAS, {"bill_start_day": 5}, "gas/IE/p/flat/all", "gas-id")
    for entry in (power, gas):
        entry.add_to_hass(hass)
    power_entity = _register(hass, power, "IE/p/flat/all", "Utility Tariff", "import_price")
    gas_entity = _register(hass, gas, "gas/IE/p/flat/all", "Gas Tariff", "gas_price")
    hass_storage[storage_key("gas-id")] = {"version": 1, "key": storage_key("gas-id"),
                                           "data": {"days": {"2026-11-13": {}}}}

    assert await hass.config_entries.async_setup(power.entry_id)
    await hass.async_block_till_done()

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.entry_id == "power-id"
    assert (entry.version, entry.title, entry.unique_id) == (2, "Utility Tariffs", DOMAIN)
    assert dict(entry.data) == {} and dict(entry.options) == {}
    assert hass.config_entries.async_get_entry("gas-id") is None
    subs = {s.subentry_type: s for s in entry.subentries.values()}
    assert set(subs) == {"electricity", "gas"}
    assert subs["electricity"].data["import_energy_entity"] == METER
    assert subs["electricity"].data["entity_key"] == "IE/p/flat/all"
    assert subs["gas"].data["bill_start_day"] == 5
    assert subs["gas"].data["service"] == "gas"
    assert subs["gas"].unique_id == "gas/IE/p/flat/all"
    # the same entity ids, now under the one entry, each in its own subentry
    registry = er.async_get(hass)
    for entity_id, service in ((power_entity, "electricity"), (gas_entity, "gas")):
        row = registry.async_get(entity_id)
        assert row is not None
        assert (row.config_entry_id, row.config_subentry_id) == (
            entry.entry_id, subs[service].subentry_id
        )
    # the saved history of the moved gas entry is not deleted with its old entry
    assert hass_storage[storage_key("gas-id")]["data"]["days"]
    assert _coordinator(entry, "gas").fuel.store_key == "gas-id"
    assert hass.states.get("sensor.gas_tariff_gas_price").state == "0.07"
    assert hass.states.get("sensor.utility_tariff_import_price").state == "0.25"


async def test_the_tariffs_are_named_for_their_fuel_and_have_no_hub_after_the_move(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str],  # noqa: F811
) -> None:
    freezer.move_to(NOON)
    await hass.config.async_set_time_zone("Europe/Dublin")
    power = _old_entry(POWER, {}, "IE/p/flat/all", "power-id")
    gas = _old_entry(GAS, {}, "gas/IE/p/flat/all", "gas-id")
    for entry in (power, gas):
        entry.add_to_hass(hass)
    _register(hass, power, "IE/p/flat/all", "Utility Tariff", "import_price")
    _register(hass, gas, "gas/IE/p/flat/all", "Gas Tariff", "gas_price")

    assert await async_setup_component(hass, DOMAIN, {})  # the start-up Home Assistant does
    await hass.async_block_till_done()

    [entry] = hass.config_entries.async_entries(DOMAIN)
    devices = dr.async_get(hass)
    found = dr.async_entries_for_config_entry(devices, entry.entry_id)
    assert {d.name for d in found} == {"Electricity tariff", "Gas tariff"}
    assert all(d.via_device_id is None for d in found)
    assert {sub.title for sub in entry.subentries.values()} == {"Electricity tariff", "Gas tariff"}


async def test_a_beta_5_install_loses_its_hub_and_gets_plain_titles(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, stores: list[str],  # noqa: F811
) -> None:
    freezer.move_to(NOON)
    await hass.config.async_set_time_zone("Europe/Dublin")
    power = _old_entry(POWER, {}, "IE/p/flat/all", "power-id")
    power.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    [entry] = hass.config_entries.async_entries(DOMAIN)
    [sub] = entry.subentries.values()
    hass.config_entries.async_update_subentry(entry, sub, title="Some Supplier Plan")
    devices = dr.async_get(hass)
    devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, hub_identifier(entry.entry_id))},
        name="Utility Tariffs",
    )

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert not [d for d in dr.async_entries_for_config_entry(devices, entry.entry_id)
                if (DOMAIN, hub_identifier(entry.entry_id)) in d.identifiers]
    assert [s.title for s in entry.subentries.values()] == ["Electricity tariff"]


async def test_one_electricity_entry_alone_keeps_its_entities(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path],
) -> None:
    freezer.move_to(NOON)
    await hass.config.async_set_time_zone("Europe/Dublin")
    old = _old_entry(DATA, {}, "IE/p/plan/urban", "only-id")  # made before the entity key
    old.add_to_hass(hass)
    entity_id = _register(hass, old, "IE/p/plan/urban", "Utility Tariff", "import_price")

    assert await hass.config_entries.async_setup(old.entry_id)
    await hass.async_block_till_done()

    [entry] = hass.config_entries.async_entries(DOMAIN)
    [sub] = entry.subentries.values()
    assert sub.data["entity_key"] == "IE/p/plan/urban"  # the key the old unique ids were built on
    row = er.async_get(hass).async_get(entity_id)
    assert row is not None and row.config_subentry_id == sub.subentry_id
    assert hass.states.get("sensor.utility_tariff_import_price") is not None
