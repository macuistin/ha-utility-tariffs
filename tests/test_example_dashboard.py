"""The example dashboard in docs/examples parses and its cards render on a real Home Assistant."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from custom_components.utility_tariffs.const import CONF_HOUSE_ENERGY, CONF_IMPORT_ENERGY
from tests.helpers import ROOT
from tests.test_bill import METER, _minute, _set
from tests.test_sensor import NOON, _setup

EXAMPLE = ROOT / "docs" / "examples" / "bill-dashboard.yaml"
HOUSE = "sensor.house_energy"


def _cards() -> list[dict[str, Any]]:
    config = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    return [c for s in config["views"][0]["sections"] for c in s["cards"]]


def test_the_file_is_a_whole_dashboard_with_a_list_of_views() -> None:
    config = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))

    assert isinstance(config["views"], list)
    assert config["views"][0]["type"] == "sections"
    assert "&gt;" not in EXAMPLE.read_text(encoding="utf-8")


async def test_every_entity_exists_and_every_card_renders(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    _set(hass, METER, 100.0)
    _set(hass, HOUSE, 50.0)
    await _setup(hass, options={CONF_IMPORT_ENERGY: METER, CONF_HOUSE_ENERGY: HOUSE})
    _set(hass, METER, 100.5)
    _set(hass, HOUSE, 51.0)
    await _minute(hass, freezer)
    cards = _cards()

    for card in cards:
        if card["type"] == "tile":
            assert hass.states.get(card["entity"]) is not None, card["entity"]
    text = EXAMPLE.read_text(encoding="utf-8")
    for entity_id in set(re.findall(r"sensor\.electricity_tariff_\w+", text)):
        assert hass.states.get(entity_id) is not None, entity_id

    rendered = [
        Template(card["content"], hass).async_render(parse_result=False)
        for card in cards
        if card["type"] == "markdown"
    ]
    everything = "\n".join(rendered)
    assert "so far" in everything  # the bill card
    assert "| Standing |" in everything  # the line table, with paid, would have paid and saved
    assert "`11-14`" in everything  # one bar for today
    assert "The bill is not available" not in everything
    assert "The lines are not available" not in everything
    assert "No days are priced" not in everything
