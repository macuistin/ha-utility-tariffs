"""The bill so far as an HTML page, from the bill_summary action."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.utility_tariffs.const import CONF_IMPORT_ENERGY, DOMAIN
from tests.test_sensor import NOON, _setup

METER = "sensor.meter_in"


async def _summary(hass: HomeAssistant, entry_id: str):
    return await hass.services.async_call(
        DOMAIN,
        "bill_summary",
        {"config_entry_id": entry_id},
        blocking=True,
        return_response=True,
    )


async def test_the_summary_is_a_page_with_the_bill_lines_and_total(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    hass.states.async_set(METER, "100", {"unit_of_measurement": "kWh"})
    entry = await _setup(hass, options={CONF_IMPORT_ENERGY: METER})
    hass.states.async_set(METER, "112", {"unit_of_measurement": "kWh"})
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    reply = await _summary(hass, entry.entry_id)

    page = reply["html"]
    assert page.startswith("<!doctype html>")
    assert "Utility Tariff" not in page.split("<h1>")[0]  # the title is the plan, not the device
    assert "<h1>P Energy Plan (Urban)</h1>" in page
    assert "Total so far" in page
    assert f"{reply['total']:,.2f} EUR" in page
    assert reply["currency"] == "EUR"
    assert reply["period_start"] == "2026-11-01"
    assert reply["next_period_start"] == "2026-12-01"
    assert "<script" not in page


async def test_a_name_with_markup_is_escaped(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    hass.states.async_set(METER, "100", {"unit_of_measurement": "kWh"})
    data = {
        "country": "IE",
        "provider": "p",
        "tariff": "plan",
        "area": "urban",
        "name": "<script>alert(1)</script>",
    }
    entry = await _setup(hass, data=data, options={CONF_IMPORT_ENERGY: METER})

    page = (await _summary(hass, entry.entry_id))["html"]

    assert "<script>" not in page
    assert "&lt;script&gt;" in page


async def test_the_summary_needs_a_meter(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    with pytest.raises(ServiceValidationError):
        await _summary(hass, entry.entry_id)
