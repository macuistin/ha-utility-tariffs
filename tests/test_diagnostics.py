"""The diagnostics report: what it holds, and what it leaves out."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.utility_tariffs.diagnostics import async_get_config_entry_diagnostics
from tests.test_sensor import DATA, NOON, _setup

METER = "sensor.grid_import_total"


async def test_the_report_holds_the_held_prices_and_hides_the_household(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass, DATA, {"import_energy_entity": METER})

    report = await async_get_config_entry_diagnostics(hass, entry)

    assert report["entry"]["data"]["area"] == "**REDACTED**"
    assert report["entry"]["data"]["provider"] == "p"
    assert report["entry"]["options"]["import_energy_entity"] == "**REDACTED**"
    held = report["coordinator"]
    assert held["last_update_success"] is True
    assert held["tariff"] == "plan-urban"
    assert held["own_rates"] is False
    assert held["slots"] > 0
    assert held["bill_kept"] is True
    assert METER not in str(report)
