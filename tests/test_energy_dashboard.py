"""The price sensors satisfy the Energy dashboard's own validation of a grid price entity."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.energy.data import async_get_manager
from homeassistant.components.energy.validate import async_validate
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.test_sensor import NOON, _setup


@pytest.fixture(autouse=True)
def _enable_custom_integrations(recorder_mock: object, enable_custom_integrations: None) -> None:
    """Start the recorder before `hass`, which the Energy dashboard needs."""


IMPORT = "sensor.electricity_tariff_import_price"
EXPORT = "sensor.electricity_tariff_export_price"
BAD = "sensor.price_without_kwh"


def _grid(energy_from: str, energy_to: str, price: str, export_price: str) -> dict[str, object]:
    return {
        "type": "grid",
        "stat_energy_from": energy_from,
        "stat_energy_to": energy_to,
        "stat_cost": None,
        "entity_energy_price": price,
        "number_energy_price": None,
        "stat_compensation": None,
        "entity_energy_price_export": export_price,
        "number_energy_price_export": None,
        "cost_adjustment_day": 0,
    }


async def test_the_dashboard_accepts_both_prices_as_grid_price_entities(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)
    assert await async_setup_component(hass, "energy", {})
    hass.states.async_set(BAD, "0.2", {"unit_of_measurement": "EUR"})
    manager = await async_get_manager(hass)
    await manager.async_update(
        {
            "energy_sources": [
                _grid("sensor.grid_in", "sensor.grid_out", IMPORT, EXPORT),
                _grid("sensor.other_in", "sensor.other_out", BAD, BAD),
            ]
        }
    )

    result = await async_validate(hass)

    everything = [
        entity
        for source in result.as_dict()["energy_sources"]
        for issue in source
        for entity, _detail in issue["affected_entities"]
    ]
    assert BAD in everything  # the validation ran and does reject a price without /kWh
    problems = [
        issue["type"]
        for source in result.as_dict()["energy_sources"]
        for issue in source
        if {IMPORT, EXPORT} & {entity for entity, _detail in issue["affected_entities"]}
    ]
    assert problems == []
