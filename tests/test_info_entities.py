"""The diagnostic entities: which tariff is followed, when its prices apply, how fresh they are."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from utility_tariffs_lib.tariffstore import folder_reader

from custom_components.utility_tariffs.const import DOMAIN
from tests.support.building import build_store
from tests.support.fixtures import tariff, write_store
from tests.test_cache_options import CountingReader
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


async def test_a_plan_that_is_ending_with_nothing_after_it_raises_a_repair(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path],
    tmp_path: Path,
) -> None:
    ending = write_store(tmp_path / "ending", {"p/plan/1.json": tariff(effective_to="2026-11-20")})
    build_store(ending)
    use_store(folder_reader(ending))
    freezer.move_to(NOON)
    entry = await _setup(hass)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"plan_ending_{entry.entry_id}")
    assert issue is not None
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["date"] == "2026-11-20"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_no_plan_ending_repair_for_an_open_ended_plan(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"plan_ending_{entry.entry_id}") is None
    await hass.config_entries.async_unload(entry.entry_id)


async def test_days_without_reaching_the_store_raise_a_repair_that_clears_when_it_is_back(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    reader = CountingReader(use_store())
    use_store(reader)
    freezer.move_to(NOON)
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    issues = ir.async_get(hass)
    issue_id = f"store_unreached_{entry.entry_id}"

    reader.down = True
    freezer.move_to("2026-11-17 12:00:00+00:00")
    await coordinator.async_refresh_store()
    assert issues.async_get_issue(DOMAIN, issue_id) is not None
    state = hass.states.get("sensor.utility_tariff_prices_last_read")
    assert state is not None and state.state == "2026-11-14T12:00:00+00:00"  # the last real read

    reader.down = False
    await coordinator.async_refresh_store()
    assert issues.async_get_issue(DOMAIN, issue_id) is None
    await hass.config_entries.async_unload(entry.entry_id)
