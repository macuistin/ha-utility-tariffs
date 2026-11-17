"""The price sensors of a followed tariff, on a real Home Assistant with a frozen clock."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import ulid as ulid_util
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


async def _setup(
    hass: HomeAssistant, data: dict[str, str] = DATA, options: dict[str, str] | None = None,
    entry_id: str | None = None,
) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Dublin")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="/".join(data[k] for k in ("country", "provider", "tariff", "area")),
        data=data, title=data["name"], options=options or {}, entry_id=entry_id or ulid_util.ulid_now(),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, key: str) -> str:
    entity_id = f"sensor.utility_tariff_{key}"
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
    assert hass.states.get("sensor.utility_tariff_import_price").attributes[
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


async def test_the_device_has_a_fixed_name_and_the_plan_as_its_model(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    freezer.move_to(NOON)
    entry = await _setup(hass)

    entity = er.async_get(hass).async_get("sensor.utility_tariff_import_price")
    assert entity is not None and entity.device_id is not None
    device = dr.async_get(hass).async_get(entity.device_id)
    assert device is not None
    assert device.name == "Utility Tariff"
    assert device.model == "Plan (Urban)"
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

    entity = er.async_get(hass).async_get(f"sensor.utility_tariff_{key}")
    assert entity is not None
    assert entity.unique_id == f"IE/p/plan/urban_{key}"


async def test_a_store_that_fails_later_keeps_the_prices_already_held(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    use_store: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess
    from custom_components.utility_tariffs.lib.tariffstore import StoreError

    freezer.move_to(NOON)
    entry = await _setup(hass)

    async def fail(self, *args, **kwargs):
        raise StoreError("down")

    monkeypatch.setattr(TariffStoreAccess, "async_definition", fail)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, "import_price") == "0.3"


async def test_the_store_is_read_again_every_night_after_midnight(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    use_store: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess

    freezer.move_to("2026-11-14 23:59:00+00:00")
    await _setup(hass)
    reads: list[object] = []
    original = TariffStoreAccess.async_definition

    async def counted(self, *args, **kwargs):
        reads.append(args)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(TariffStoreAccess, "async_definition", counted)
    freezer.move_to("2026-11-15 00:05:00+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(reads) == 1
    assert _state(hass, "next_price_change") == "2026-11-15T08:00:00+00:00"
