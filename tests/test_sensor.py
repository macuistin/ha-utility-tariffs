"""The price sensors of a followed tariff, on a real Home Assistant with a frozen clock."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.utility_tariffs.const import DOMAIN

NOON = "2026-11-14 12:00:00+00:00"
DATA = {
    "country": "IE",
    "provider": "p",
    "tariff": "plan",
    "area": "urban",
    "name": "P Energy Plan (Urban)",
}


async def _setup(hass: HomeAssistant, data: dict[str, str] = DATA) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Dublin")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="/".join(data[k] for k in ("country", "provider", "tariff", "area")),
        data=data, title=data["name"],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, key: str) -> str:
    entity_id = f"sensor.p_energy_plan_urban_{key}"
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state


async def test_the_prices_and_band_in_force_now(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert _state(hass, "import_price") == "0.3"
    assert _state(hass, "import_rate_band") == "Day"
    assert hass.states.get("sensor.p_energy_plan_urban_import_price").attributes[
        "unit_of_measurement"
    ] == "EUR/kWh"


async def test_the_next_change_is_when_the_band_next_changes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert _state(hass, "next_price_change") == "2026-11-14T23:00:00+00:00"
    assert _state(hass, "next_import_price") == "0.15"


async def test_the_sensors_follow_the_clock_at_the_half_hour(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to("2026-11-14 22:59:00+00:00")
    await _setup(hass)
    assert _state(hass, "import_rate_band") == "Day"

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert _state(hass, "import_rate_band") == "Night"
    assert _state(hass, "import_price") == "0.15"


async def test_the_device_is_named_for_the_plan(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    freezer.move_to(NOON)
    entry = await _setup(hass)

    entity = er.async_get(hass).async_get("sensor.p_energy_plan_urban_import_price")
    assert entity is not None and entity.device_id is not None
    device = dr.async_get(hass).async_get(entity.device_id)
    assert device is not None
    assert device.name == "P Energy Plan (Urban)"
    assert device.manufacturer == "P Energy"
    assert entry.state is ConfigEntryState.LOADED


async def test_a_store_that_cannot_be_read_at_start_retries_later(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    def unreachable(path: str) -> bytes:
        raise OSError("no network")

    use_store(unreachable)
    freezer.move_to(NOON)
    await hass.config.async_set_time_zone("Europe/Dublin")
    entry = MockConfigEntry(domain=DOMAIN, unique_id="IE/p/plan/urban", data=DATA)
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize("key", ["import_price", "next_price_change"])
async def test_every_sensor_has_a_unique_id_from_the_plan(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path], key: str
) -> None:
    from homeassistant.helpers import entity_registry as er

    freezer.move_to(NOON)
    await _setup(hass)

    entity = er.async_get(hass).async_get(f"sensor.p_energy_plan_urban_{key}")
    assert entity is not None
    assert entity.unique_id == f"IE/p/plan/urban_{key}"
