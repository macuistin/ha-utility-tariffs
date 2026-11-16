"""The previous price, day figures, rating and the get_prices action, on a real Home Assistant."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.utility_tariffs.const import DOMAIN
from tests.test_sensor import NOON, _setup, _state


async def test_the_previous_price_is_the_one_before_the_current_band(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert _state(hass, "previous_import_price") == "0.15"


async def test_the_previous_price_is_known_just_after_midnight(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to("2026-11-15 00:30:00+00:00")  # night since 23:00, day before it at 0.30
    await _setup(hass)

    assert _state(hass, "import_price") == "0.15"
    assert _state(hass, "previous_import_price") == "0.3"


async def test_the_day_figures_weight_each_price_by_its_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert _state(hass, "lowest_import_price_today") == "0.15"
    assert _state(hass, "highest_import_price_today") == "0.3"
    # 9 hours at 0.15 and 15 hours at 0.30
    assert float(_state(hass, "average_import_price_today")) == pytest.approx(0.24375)


async def test_the_export_day_figures_are_off_until_asked_for(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    registry = er.async_get(hass)
    for key in ("lowest", "highest", "average"):
        entity = registry.async_get(f"sensor.p_energy_plan_urban_{key}_export_price_today")
        assert entity is not None and entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert registry.async_get("sensor.p_energy_plan_urban_lowest_import_price_today").disabled_by is None


async def test_the_rating_places_the_price_in_the_day(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert _state(hass, "import_price_rating") == "very_high"
    freezer.move_to("2026-11-14 03:00:00+00:00")
    await hass.config_entries.async_reload(hass.config_entries.async_entries(DOMAIN)[0].entry_id)
    await hass.async_block_till_done()
    assert _state(hass, "import_price_rating") == "very_low"


async def _prices(hass: HomeAssistant, entry_id: str, **fields: str) -> dict:
    return await hass.services.async_call(
        DOMAIN, "get_prices", {"config_entry_id": entry_id, **fields},
        blocking=True, return_response=True,
    )


async def test_get_prices_returns_each_stretch_cut_to_the_range(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    reply = await _prices(
        hass, entry.entry_id, start="2026-11-14 22:00:00", end="2026-11-15 01:00:00"
    )

    assert reply["currency"] == "EUR" and reply["unit"] == "EUR/kWh"
    assert reply["complete"] is True
    assert reply["prices"] == [
        {"start": "2026-11-14T22:00:00+00:00", "end": "2026-11-14T23:00:00+00:00",
         "import_price": 0.3, "export_price": 0.0, "import_band": "Day", "export_band": "Export"},
        {"start": "2026-11-14T23:00:00+00:00", "end": "2026-11-15T01:00:00+00:00",
         "import_price": 0.15, "export_price": 0.0, "import_band": "Night", "export_band": "Export"},
    ]


async def test_get_prices_defaults_to_the_next_day_from_now(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    reply = await _prices(hass, entry.entry_id)

    assert reply["prices"][0]["start"] == "2026-11-14T12:00:00+00:00"
    assert reply["prices"][-1]["end"] == "2026-11-15T12:00:00+00:00"


async def test_get_prices_says_when_the_range_goes_past_the_held_prices(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    reply = await _prices(
        hass, entry.entry_id, start="2026-11-15 20:00:00", end="2026-11-17 06:00:00"
    )

    assert reply["complete"] is False
    assert reply["prices"][-1]["end"] == "2026-11-16T00:00:00+00:00"


async def test_get_prices_for_a_range_with_no_prices_is_empty_not_complete(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    reply = await _prices(hass, entry.entry_id, start="2026-12-01 00:00:00", end="2026-12-02 00:00:00")

    assert reply["prices"] == [] and reply["complete"] is False


async def test_get_prices_refuses_an_end_before_the_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    with pytest.raises(ServiceValidationError):
        await _prices(hass, entry.entry_id, start="2026-11-14 12:00:00", end="2026-11-14 11:00:00")
