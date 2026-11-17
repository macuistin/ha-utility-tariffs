"""The diagnostic entities: which tariff is followed, when its prices apply, how fresh they are."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from tests.test_sensor import NOON, _setup


async def test_the_dates_the_prices_apply_are_shown(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert hass.states.get("sensor.utility_tariff_prices_valid_from").state == "2026-11-01"
    assert hass.states.get("sensor.utility_tariff_prices_valid_to").state == "unknown"


async def test_the_time_of_the_last_read_is_shown(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert hass.states.get("sensor.utility_tariff_prices_last_read").state == (
        "2026-11-14T12:00:00+00:00"
    )


async def test_the_summary_names_the_plan_and_describes_it(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    state = hass.states.get("sensor.utility_tariff_tariff_summary")
    assert state is not None
    attributes = state.attributes
    assert attributes["provider"] == "P Energy"
    assert attributes["currency"] == "EUR"
    assert attributes["revision"] == 1
    assert attributes["valid_from"] == "2026-11-01"
    assert attributes["valid_to"] is None
    assert attributes["own_rates"] is False
    assert attributes["store_offline"] is False
    assert set(attributes["import_prices"]) == {"Day", "Night"}


async def test_the_store_is_not_offline_when_it_can_be_read(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert hass.states.get("binary_sensor.utility_tariff_tariff_store_offline").state == "off"
    assert hass.states.get("binary_sensor.utility_tariff_tomorrow_s_prices_available") is None
