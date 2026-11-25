"""The off-peak sensor: two bands, three bands and a flat tariff."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from utility_tariffs_lib.tariff import PriceSlot

from custom_components.utility_tariffs.off_peak import Stretch, around, off_peak_stretches
from tests.test_sensor import DATA, NOON, _setup

DAY = datetime(2026, 11, 14, tzinfo=UTC)


def _slots(prices: list[str]) -> list[PriceSlot]:
    """One slot per hour from midnight, one price each."""
    return [
        PriceSlot(
            DAY + timedelta(hours=hour),
            DAY + timedelta(hours=hour + 1),
            f"band{price}",
            "export",
            Decimal(price),
            Decimal("0"),
        )
        for hour, price in enumerate(prices)
    ]


def test_a_two_band_tariff_has_one_off_peak_stretch_per_night() -> None:
    stretches = off_peak_stretches(_slots(["0.1"] * 2 + ["0.3"] * 20 + ["0.1"] * 2))

    assert stretches == [
        Stretch(DAY, DAY + timedelta(hours=2)),
        Stretch(DAY + timedelta(hours=22), DAY + timedelta(hours=24)),
    ]


def test_off_peak_is_the_lowest_band_of_a_three_band_tariff_only() -> None:
    prices = ["0.1"] * 3 + ["0.2"] * 4 + ["0.3"] * 17
    [stretch] = off_peak_stretches(_slots(prices)) or []

    assert (stretch.start, stretch.end) == (DAY, DAY + timedelta(hours=3))


def test_a_flat_tariff_has_no_off_peak() -> None:
    assert off_peak_stretches(_slots(["0.25"] * 24)) is None
    assert off_peak_stretches([]) is None


def test_the_current_and_next_stretch() -> None:
    stretches = [
        Stretch(DAY, DAY + timedelta(hours=2)),
        Stretch(DAY + timedelta(hours=22), DAY + timedelta(hours=24)),
    ]

    inside = around(stretches, DAY + timedelta(hours=1))
    outside = around(stretches, DAY + timedelta(hours=12))

    assert inside == (stretches[0], stretches[1])
    assert outside == (None, stretches[1])
    assert around(stretches, DAY + timedelta(hours=23)) == (stretches[1], None)


async def test_the_sensor_is_off_by_day_with_the_next_night_as_attributes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    state = hass.states.get("binary_sensor.electricity_tariff_off_peak")

    assert state is not None
    assert state.state == "off"
    assert state.attributes["current_start"] is None
    assert state.attributes["next_start"] == "2026-11-14T23:00:00+00:00"
    assert state.attributes["next_end"] == "2026-11-15T08:00:00+00:00"


async def test_the_sensor_is_on_at_night_with_the_current_stretch(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to("2026-11-14 23:30:00+00:00")
    await _setup(hass)

    state = hass.states.get("binary_sensor.electricity_tariff_off_peak")

    assert state is not None
    assert state.state == "on"
    assert state.attributes["current_start"] == "2026-11-14T23:00:00+00:00"
    assert state.attributes["current_end"] == "2026-11-15T08:00:00+00:00"


async def test_a_flat_tariff_is_unavailable_not_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    flat = {**DATA, "tariff": "flat", "area": "all", "name": "Flat"}
    await _setup(hass, flat)

    state = hass.states.get("binary_sensor.electricity_tariff_off_peak")

    assert state is not None
    assert state.state == "unavailable"
