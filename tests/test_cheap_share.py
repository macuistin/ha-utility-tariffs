"""The share of the imported electricity used in the tariff's cheapest band."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from utility_tariffs_lib.tariff import SlotEnergy

from custom_components.utility_tariffs.cheap_share import CheapShare, cheap_bands
from custom_components.utility_tariffs.const import CONF_IMPORT_ENERGY
from tests.test_sensor import DATA, NOON, _setup

METER = "sensor.meter_in"
DAY = "sensor.utility_tariff_cheap_electricity_used_today"
PERIOD = "sensor.utility_tariff_cheap_electricity_used_this_bill_period"
THIRTY = "sensor.utility_tariff_cheap_electricity_used_last_30_days"


def _at(hour: int, day: int = 14) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def test_the_cheap_bands_are_the_lowest_priced() -> None:
    prices = {"Day": Decimal("0.3"), "Night": Decimal("0.15"), "Boost": Decimal("0.15")}

    assert cheap_bands(prices) == {"Night", "Boost"}


def test_a_tariff_with_one_price_has_no_cheap_band() -> None:
    assert cheap_bands({"A": Decimal("0.2"), "B": Decimal("0.2")}) == frozenset()


def test_nothing_imported_is_a_share_of_zero() -> None:
    assert CheapShare(0.0, 0.0).percent == 0.0


async def _meter_setup(hass: HomeAssistant, freezer: FrozenDateTimeFactory, plan: str = "plan"):
    freezer.move_to(NOON)
    hass.states.async_set(METER, "100", {"unit_of_measurement": "kWh"})
    data = DATA if plan == "plan" else {**DATA, "tariff": "flat", "area": "all"}
    entry = await _setup(hass, data, options={CONF_IMPORT_ENERGY: METER})
    accountant = entry.runtime_data.accountant
    assert accountant is not None
    return entry, accountant


def _book(accountant, kwh: float, hour: int, day: int = 14) -> None:  # type: ignore[no-untyped-def]
    start = _at(hour, day)
    accountant.store.record(
        SlotEnergy(flows={"import": kwh}), start, start.replace(minute=30)
    )


async def test_the_share_is_the_energy_in_the_cheapest_band(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    entry, accountant = await _meter_setup(hass, freezer)
    _book(accountant, 1.0, 2)  # night, 0.15
    _book(accountant, 3.0, 10)  # day, 0.30
    entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get(DAY)

    assert state is not None
    assert float(state.state) == 25.0
    assert state.attributes["cheap_kwh"] == 1.0
    assert state.attributes["imported_kwh"] == 4.0
    assert state.attributes["unit_of_measurement"] == "%"


async def test_the_bill_period_counts_earlier_days_and_today_does_not(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    entry, accountant = await _meter_setup(hass, freezer)
    _book(accountant, 2.0, 10)  # today, day rate
    _book(accountant, 2.0, 2, day=12)  # two days back, night rate
    entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()

    assert float(hass.states.get(DAY).state) == 0.0  # type: ignore[union-attr]
    assert float(hass.states.get(PERIOD).state) == 50.0  # type: ignore[union-attr]


async def test_a_flat_tariff_shows_zero_and_is_not_unavailable(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    entry, accountant = await _meter_setup(hass, freezer, plan="flat")
    _book(accountant, 2.0, 10)
    entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get(DAY)

    assert state is not None
    assert float(state.state) == 0.0


async def test_the_thirty_day_sensor_is_off_until_enabled(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _meter_setup(hass, freezer)

    assert hass.states.get(THIRTY) is None


async def test_there_are_no_cheap_sensors_without_a_meter(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert hass.states.get(DAY) is None


@pytest.mark.parametrize("hour", [7, 23])
async def test_the_band_edges_follow_the_tariff(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path], hour: int
) -> None:
    entry, accountant = await _meter_setup(hass, freezer)
    _book(accountant, 1.0, hour, day=13 if hour == 23 else 14)
    entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get(PERIOD)

    assert state is not None
    assert float(state.state) == 100.0  # 07:00 and 23:00 are both in the night band
