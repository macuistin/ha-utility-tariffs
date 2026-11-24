"""Suggesting a cheaper plan: the ranking of the store's plans over the last whole bill."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from utility_tariffs_lib.tariff import SlotEnergy
from utility_tariffs_lib.tariffstore import StoreError

from custom_components.utility_tariffs.const import CONF_IMPORT_ENERGY, DOMAIN
from tests.test_sensor import NOON, _coordinator, _setup, _state

METER = "sensor.meter_in"
DUBLIN = ZoneInfo("Europe/Dublin")
TODAY = date(2026, 11, 14)


def _fill_october(coordinator, kwh_per_slot: float = 0.5) -> None:
    """Half-hourly import for every day of October, so the last whole bill is recorded."""
    history = coordinator.accountant.store.history
    cursor = datetime(2026, 10, 1, tzinfo=DUBLIN)
    while cursor.month == 10:
        end = cursor + timedelta(minutes=30)
        history.record(SlotEnergy({"import": kwh_per_slot}), cursor, end)
        cursor = end


async def _entry(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    freezer.move_to(NOON)
    hass.states.async_set(METER, "100", {"unit_of_measurement": "kWh"})
    return await _setup(hass, options={CONF_IMPORT_ENERGY: METER})


async def test_no_ranking_sensors_without_a_meter(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    await _setup(hass)

    assert hass.states.get("sensor.utility_tariff_plan_rank") is None


async def test_no_rank_until_a_bill_is_recorded(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    await _entry(hass, freezer)
    await hass.async_block_till_done()

    assert _state(hass, "plan_rank") == "unknown"


async def test_a_cheaper_plan_is_ranked_first_and_suggested(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    entry = await _entry(hass, freezer)
    coordinator = _coordinator(entry)
    _fill_october(coordinator)

    await coordinator.ranker.async_refresh(TODAY)
    coordinator.async_update_listeners()

    assert _state(hass, "plan_rank") == "2"
    assert float(_state(hass, "cheapest_plan_saving")) > 0
    attributes = hass.states.get("sensor.utility_tariff_plan_rank").attributes
    assert attributes["plans_compared"] == 2
    assert attributes["top_plans"][0]["plan"] == "P Energy Flat"
    assert attributes["top_plans"][1]["yours"] is True
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "cheaper_plan")
    assert issue is not None
    saving = hass.states.get("sensor.utility_tariff_cheapest_plan_saving").attributes
    ranking = coordinator.ranker.ranking
    assert saving["days_recorded"] == ranking.days_recorded > 0
    assert saving["period_start"] == ranking.first_day.isoformat()
    assert issue.translation_placeholders["days"] == str(ranking.days_recorded)
    assert issue.translation_placeholders["last"] == ranking.last_day.isoformat()


async def test_the_cheapest_plan_raises_no_suggestion(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    entry = await _entry(hass, freezer)
    coordinator = _coordinator(entry)
    _fill_october(coordinator)
    await coordinator.ranker.async_refresh(TODAY)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "cheaper_plan") is not None

    # Following the cheaper plan instead leaves nothing cheaper to suggest.
    sub = next(iter(entry.subentries.values()))
    hass.config_entries.async_update_subentry(
        entry, sub, data={**sub.data, "tariff": "flat", "area": "all"}
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = _coordinator(entry)
    _fill_october(coordinator)
    await coordinator.ranker.async_refresh(TODAY)

    assert coordinator.ranker.ranking.current_rank == 1
    assert coordinator.ranker.ranking.saving == 0
    assert ir.async_get(hass).async_get_issue(DOMAIN, "cheaper_plan") is None


async def test_a_store_that_cannot_be_read_keeps_the_last_ranking(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    use_store: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = await _entry(hass, freezer)
    coordinator = _coordinator(entry)
    _fill_october(coordinator)
    kept = await coordinator.ranker.async_refresh(TODAY)

    async def down(*args, **kwargs):
        raise StoreError("down")

    monkeypatch.setattr("custom_components.utility_tariffs.plan_ranker.gather", down)
    again = await coordinator.ranker.async_refresh(TODAY)

    assert kept is not None
    assert again is None
    assert coordinator.ranker.ranking == kept
