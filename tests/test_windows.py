"""The window sensors, the options flow and the find_window action, on a real Home Assistant."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.utility_tariffs.const import DOMAIN
from tests.options_support import configure
from tests.test_sensor import NOON, _setup, _state

TIMES = "2026-11-14 22:00:00+00:00"


def _binary(hass: HomeAssistant, which: str = "cheapest") -> str:
    state = hass.states.get(f"binary_sensor.utility_tariff_{which}_window_active")
    assert state is not None
    return state.state


async def test_the_cheapest_window_is_the_first_stretch_at_the_night_price(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert _state(hass, "cheapest_window_start") == "2026-11-14T23:00:00+00:00"
    assert _state(hass, "cheapest_window_end") == "2026-11-15T08:00:00+00:00"
    assert _binary(hass) == "off"


async def test_the_dearest_window_may_already_be_under_way(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    # Two hours ending after 12:05 and starting on the half hour: the earliest at the day price.
    assert _state(hass, "dearest_window_start") == "2026-11-14T10:30:00+00:00"


async def test_a_dearest_window_under_way_has_a_past_start_a_future_end_and_is_active(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    # The start is behind us because the window began at 10:30, so the end and the active sensor
    # say it is current, not a later one. The end is where the day price stops, not start + two hours.
    assert _state(hass, "dearest_window_start") == "2026-11-14T10:30:00+00:00"
    assert _state(hass, "dearest_window_end") == "2026-11-14T23:00:00+00:00"
    assert _binary(hass, "dearest") == "on"
    assert _binary(hass, "cheapest") == "off"


async def test_the_window_is_active_once_it_has_started_and_stays_the_answer(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to("2026-11-14 22:30:00+00:00")
    await _setup(hass)
    assert _binary(hass) == "off"

    freezer.move_to("2026-11-14 23:30:00+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert _binary(hass) == "on"
    assert _state(hass, "cheapest_window_start") == "2026-11-14T23:00:00+00:00"


async def test_a_longer_window_from_the_options_is_used(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    result = await configure(hass, entry.entry_id, windows={"window_minutes": 360})
    await hass.async_block_till_done()

    assert result["data"] == {"window_minutes": 360}
    assert _state(hass, "cheapest_window_end") == "2026-11-15T08:00:00+00:00"


async def test_the_action_finds_the_cheapest_window_and_its_cost(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    reply = await hass.services.async_call(
        DOMAIN,
        "find_window",
        {"config_entry_id": entry.entry_id, "duration": "01:00:00", "power_kw": 2},
        blocking=True,
        return_response=True,
    )

    assert reply["found"] is True
    assert reply["start"] == "2026-11-14T23:00:00+00:00"
    assert reply["end"] == "2026-11-15T00:00:00+00:00"
    assert reply["cost"] == pytest.approx(0.30)  # 2 kW for 1 hour at 0.15
    assert reply["average_price"] == pytest.approx(0.15)
    assert reply["saving"] == pytest.approx(0.30)  # against starting now at 0.30
    assert reply["currency"] == "EUR"


async def test_the_action_can_look_for_the_dearest_and_finish_by_a_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    reply = await hass.services.async_call(
        DOMAIN,
        "find_window",
        {
            "config_entry_id": entry.entry_id,
            "duration": "01:00:00",
            "highest": True,
            "latest_end": "2026-11-14 18:00:00",
        },
        blocking=True,
        return_response=True,
    )

    assert reply["found"] is True
    assert reply["start"] == "2026-11-14T12:00:00+00:00"  # the earliest start allowed is now


async def test_the_action_says_when_nothing_fits(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    reply = await hass.services.async_call(
        DOMAIN,
        "find_window",
        {"config_entry_id": entry.entry_id, "duration": "05:00:00", "latest_end": "2026-11-14 14:00:00"},
        blocking=True,
        return_response=True,
    )

    assert reply == {"found": False}


async def test_the_action_refuses_an_entry_it_does_not_know(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "find_window",
            {"config_entry_id": "nope", "duration": "01:00:00"},
            blocking=True,
            return_response=True,
        )


async def test_the_action_refuses_a_tariff_that_is_not_loaded(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)
    await hass.config_entries.async_unload(entry.entry_id)

    with pytest.raises(ServiceValidationError, match="not loaded"):
        await hass.services.async_call(
            DOMAIN,
            "find_window",
            {"config_entry_id": entry.entry_id, "duration": "01:00:00"},
            blocking=True,
            return_response=True,
        )


async def test_a_time_with_its_own_offset_is_used_as_given(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    reply = await hass.services.async_call(
        DOMAIN,
        "find_window",
        {
            "config_entry_id": entry.entry_id,
            "duration": "01:00:00",
            "highest": True,
            "earliest_start": "2026-11-14T15:00:00+00:00",
        },
        blocking=True,
        return_response=True,
    )

    assert reply["start"] == "2026-11-14T15:00:00+00:00"


async def test_the_window_end_follows_the_band_not_the_search_length(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    # A two hour search inside a 15 hour day band: the end is the end of the band.
    start = _state(hass, "dearest_window_start")
    end = _state(hass, "dearest_window_end")
    assert end == "2026-11-14T23:00:00+00:00"
    assert end > start
