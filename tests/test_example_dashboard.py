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


def _text() -> str:
    """The file with the device name the test setup gives (the example uses a service prefix)."""
    return EXAMPLE.read_text(encoding="utf-8").replace(
        "service_electricity_tariff", "electricity_tariff"
    )


def _cards() -> list[dict[str, Any]]:
    config = yaml.safe_load(_text())
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
    hass.states.async_set(
        "sensor.electricity_tariff_plan_rank",
        "1",
        {
            "summary": "Your plan is the cheapest of the 2 compared.",
            "plans_compared": 2,
            "period_start": "2026-10-16",
            "period_end": "2026-11-15",
            "days_recorded": 31,
            "top_plans": [
                {"rank": 1, "plan": "Mine", "bill": 100.0, "yours": True},
                {"rank": 2, "plan": "Other <b>plan</b>", "bill": 120.0, "yours": False},
            ],
        },
    )
    cards = _cards()

    for card in cards:
        if card["type"] == "tile":
            assert hass.states.get(card["entity"]) is not None, card["entity"]
    text = _text()
    for entity_id in set(re.findall(r"sensor\.electricity_tariff_\w+", text)):
        assert hass.states.get(entity_id) is not None, entity_id

    rendered = [
        Template(card["content"], hass).async_render(parse_result=False)
        for card in cards
        if card["type"] == "markdown"
    ]
    everything = "\n".join(rendered)
    assert "so far" in everything  # the bill card
    assert "<td>Standing</td>" in everything  # the line table, with paid, would have paid and saved
    assert "Sat 14 Nov" in everything  # one row for today, with its bar
    assert "<img src=\"data:image/svg+xml," in everything  # the bars
    assert "Your plan</b> 100.00" in everything  # the ranking, with its own plan named
    assert "Other &lt;b&gt;plan&lt;/b&gt;" in everything  # a plan name is escaped
    assert "The bill is not available" not in everything
    assert "The lines are not available" not in everything
    assert "No days are priced" not in everything


def test_the_chart_card_uses_only_chart_types_the_card_accepts() -> None:
    allowed = {"line", "scatter", "pie", "donut", "radialBar"}  # apexcharts-card 2.2
    charts = [c for c in _cards() if c["type"] == "custom:apexcharts-card"]

    assert charts
    for chart in charts:
        assert chart.get("chart_type", "line") in allowed
        assert chart["all_series_config"]["type"] == "column"  # bars are a series type
