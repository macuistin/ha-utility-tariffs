"""The tariff status: current, ending, ended or withdrawn, worked out from the store's data."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
from utility_tariffs_lib.tariffstore import folder_reader

from custom_components.utility_tariffs.const import DOMAIN
from tests.support.building import build_store
from tests.support.fixtures import flat, tariff, write_store
from tests.test_sensor import DATA, NOON, _setup

STATUS = "sensor.utility_tariff_tariff_status"


class Swap:
    """A reader that answers from one store, and from another once `now` is replaced."""

    def __init__(self, first: Path) -> None:
        self.folder = first

    def __call__(self, path: str) -> bytes:
        return folder_reader(self.folder)(path)


def _store(root: Path, name: str, files: dict[str, dict]) -> Path:
    folder = write_store(root / name, files)
    build_store(folder)
    return folder


def _issue(hass: HomeAssistant, key: str, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}_{entry.entry_id}")


async def test_a_plan_on_offer_is_current(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    freezer.move_to(NOON)
    entry = await _setup(hass)

    state = hass.states.get(STATUS)
    assert state is not None and state.state == "current"
    assert state.attributes["needs_attention"] is False
    assert state.attributes["valid_to"] is None
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_plan_with_an_end_date_close_and_nothing_after_it_is_ending(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path],
    tmp_path: Path,
) -> None:
    ending = _store(tmp_path, "ending", {"p/plan/1.json": tariff(effective_to="2026-11-20")})
    use_store(folder_reader(ending))
    freezer.move_to(NOON)
    entry = await _setup(hass)

    state = hass.states.get(STATUS)
    assert state is not None and state.state == "ending"
    assert state.attributes["valid_to"] == "2026-11-20"
    assert state.attributes["needs_attention"] is False
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_plan_whose_prices_have_ended_is_marked_and_a_repair_is_raised(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path],
    tmp_path: Path,
) -> None:
    ended = _store(tmp_path, "ended", {"p/plan/1.json": tariff(effective_to="2026-11-16")})
    swap = Swap(use_store())
    use_store(swap)
    freezer.move_to(NOON)
    entry = await _setup(hass)
    assert hass.states.get(STATUS).state == "current"  # type: ignore[union-attr]

    swap.folder = ended
    freezer.move_to("2026-11-17 12:00:00+00:00")
    await entry.runtime_data.async_refresh_store()
    await hass.async_block_till_done()

    state = hass.states.get(STATUS)
    assert state is not None and state.state == "ended"
    assert state.attributes["needs_attention"] is True
    assert hass.states.get("sensor.utility_tariff_import_price").state == "0.3"  # type: ignore[union-attr]
    issue = _issue(hass, "plan_ended", entry)
    assert issue is not None
    assert issue.translation_placeholders == {"tariff": DATA["name"]}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_plan_the_store_no_longer_lists_is_withdrawn_and_the_repair_clears_when_it_returns(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path],
    tmp_path: Path,
) -> None:
    kept = use_store()
    gone = _store(tmp_path, "gone", {"p/flat/1.json": flat()})
    swap = Swap(kept)
    use_store(swap)
    freezer.move_to(NOON)
    entry = await _setup(hass)

    swap.folder = gone
    await entry.runtime_data.async_refresh_store()
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "withdrawn"  # type: ignore[union-attr]
    assert _issue(hass, "plan_withdrawn", entry) is not None
    assert _issue(hass, "plan_ended", entry) is None

    swap.folder = kept
    await entry.runtime_data.async_refresh_store()
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "current"  # type: ignore[union-attr]
    assert _issue(hass, "plan_withdrawn", entry) is None
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_store_that_cannot_be_reached_does_not_call_the_plan_gone(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    from tests.test_cache_options import CountingReader

    reader = CountingReader(use_store())
    use_store(reader)
    freezer.move_to(NOON)
    entry = await _setup(hass)

    reader.down = True
    await entry.runtime_data.async_refresh_store(clear=False)
    await hass.async_block_till_done()

    assert hass.states.get(STATUS).state == "current"  # type: ignore[union-attr]
    assert _issue(hass, "plan_ended", entry) is None
    assert _issue(hass, "plan_withdrawn", entry) is None
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_plan_that_has_ended_at_start_retries_and_says_why(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path],
    tmp_path: Path,
) -> None:
    ended = _store(tmp_path, "ended", {"p/plan/1.json": tariff(effective_to="2026-11-10")})
    use_store(folder_reader(ended))
    freezer.move_to(NOON)
    await hass.config.async_set_time_zone("Europe/Dublin")
    entry = MockConfigEntry(domain=DOMAIN, unique_id="IE/p/plan/urban", data=DATA, title=DATA["name"])
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "no longer prices" in (entry.reason or "")
    assert _issue(hass, "plan_ended", entry) is not None
