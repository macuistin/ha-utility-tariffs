"""The price sensor of each rate band: two bands, three, many, a flat tariff and a revision."""

from __future__ import annotations

from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from utility_tariffs_lib.tariffstore import AsyncMemoryCache, AsyncStore, folder_reader

from custom_components.utility_tariffs import coordinator, plan_steps
from custom_components.utility_tariffs.helper.store_access import TariffStoreAccess
from tests.helpers import async_reader
from tests.support.building import build_store
from tests.support.fixtures import flat, tariff, write_store
from tests.test_sensor import DATA, NOON, _setup

THREE = [{"name": "Day"}, {"name": "Night", "hours": "23:00-08:00"},
         {"name": "Peak", "hours": "17:00-19:00"}]
FOUR = [*THREE, {"name": "Boost", "hours": "02:00-04:00"}]


def _plan(bands: list[dict], rates: dict[str, str], start: str = "2026-11-01") -> dict:
    return tariff(bands=bands, effective_from=start,
                  areas={"all": {"standing": "1", "rates": rates}})


@pytest.fixture
def store(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    files = {
        "p/three/1.json": _plan(THREE, {"Day": "0.3", "Night": "0.1", "Peak": "0.4"}),
        "p/four/1.json": _plan(FOUR, {"Day": "0.3", "Night": "0.1", "Peak": "0.4", "Boost": "0.05"}),
        "p/flat/1.json": flat(),
        "p/grow/1.json": _plan(THREE[:2], {"Day": "0.3", "Night": "0.1"}),
        "p/grow/2.json": _plan(THREE, {"Day": "0.3", "Night": "0.1", "Peak": "0.4"}, "2026-11-20"),
        "p/shrink/1.json": _plan(THREE, {"Day": "0.3", "Night": "0.1", "Peak": "0.4"}),
        "p/shrink/2.json": _plan(THREE[:2], {"Day": "0.3", "Night": "0.1"}, "2026-11-20"),
    }
    folder = write_store(tmp_path, files)
    build_store(folder)
    access = TariffStoreAccess(
        hass, AsyncStore(async_reader(folder_reader(folder)), AsyncMemoryCache())
    )
    monkeypatch.setattr(plan_steps, "store_access", lambda _hass, _service="electricity": access)
    monkeypatch.setattr(coordinator, "store_access", lambda _hass, _service="electricity": access)


def _data(tariff_id: str) -> dict[str, str]:
    return {**DATA, "tariff": tariff_id, "area": "all", "name": tariff_id}


async def test_a_two_band_tariff_shows_both_prices_at_any_time_of_day(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, store: None
) -> None:
    freezer.move_to(NOON)  # the day band is in force, and the night price is still shown
    await _setup(hass, _data("grow"))

    day = hass.states.get("sensor.electricity_tariff_import_price_day")
    night = hass.states.get("sensor.electricity_tariff_import_price_night")
    assert day is not None
    assert night is not None
    assert (day.state, night.state) == ("0.3", "0.1")
    assert hass.states.get("sensor.electricity_tariff_import_price").state == "0.3"  # type: ignore[union-attr]


async def test_a_three_band_tariff_shows_every_band(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, store: None
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, _data("three"))

    for band, price in {"day": "0.3", "night": "0.1", "peak": "0.4"}.items():
        state = hass.states.get(f"sensor.electricity_tariff_import_price_{band}")
        assert state is not None, band
        assert state.state == price
        assert state.attributes["unit_of_measurement"] == "EUR/kWh"


async def test_a_flat_tariff_has_one_band_price(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, store: None
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, _data("flat"))

    state = hass.states.get("sensor.electricity_tariff_import_price_all_day")
    assert state is not None
    assert state.state == "0.25"


async def test_more_than_three_bands_start_disabled(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, store: None
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, _data("four"))

    registry = er.async_get(hass)
    band_entries = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if "_import_band_price_" in (e.unique_id or "")
    ]
    assert len(band_entries) == 4
    assert all(e.disabled_by is er.RegistryEntryDisabler.INTEGRATION for e in band_entries)
    assert hass.states.get("sensor.electricity_tariff_import_price_boost") is None


async def test_a_revision_that_adds_a_band_adds_its_sensor_without_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, store: None
) -> None:
    freezer.move_to("2026-11-19 23:59:00+00:00")
    await _setup(hass, _data("grow"))
    assert hass.states.get("sensor.electricity_tariff_import_price_peak") is None

    freezer.move_to("2026-11-20 00:06:00+00:00")  # after the nightly read
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.electricity_tariff_import_price_peak")
    assert state is not None
    assert state.state == "0.4"


async def test_a_revision_that_drops_a_band_removes_its_sensor(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, store: None
) -> None:
    freezer.move_to("2026-11-19 23:59:00+00:00")
    entry = await _setup(hass, _data("shrink"))
    assert hass.states.get("sensor.electricity_tariff_import_price_peak") is not None

    freezer.move_to("2026-11-20 00:06:00+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert hass.states.get("sensor.electricity_tariff_import_price_peak") is None
    assert not [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if (e.unique_id or "").endswith("_import_band_price_peak")
    ]
    assert hass.states.get("sensor.electricity_tariff_import_price_night") is not None
