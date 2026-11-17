"""Reading the tariff store again, or deleting the saved files, from the options."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from utility_tariffs_lib.tariffstore import folder_reader

from tests.test_sensor import NOON, _setup


class CountingReader:
    """Reads a built store from disk, counts each path, and can be made to fail."""

    def __init__(self, folder: Path) -> None:
        self._read = folder_reader(folder)
        self.reads: list[str] = []
        self.down = False

    def __call__(self, path: str) -> bytes:
        if self.down:
            raise OSError("no network")
        self.reads.append(path)
        return self._read(path)

    def count(self, ending: str) -> int:
        return sum(path.endswith(ending) for path in self.reads)


async def _finish(hass: HomeAssistant, entry_id: str) -> None:
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry_id)


async def _save(hass: HomeAssistant, entry_id: str, **actions: bool) -> dict:
    flow = await hass.config_entries.options.async_init(entry_id)
    return await hass.config_entries.options.async_configure(
        flow["flow_id"], {"window_minutes": 120, **actions}
    )


async def test_refresh_reads_the_store_index_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    reader = CountingReader(use_store())
    use_store(reader)
    freezer.move_to(NOON)
    entry = await _setup(hass)
    before = reader.count("index.json")

    result = await _save(hass, entry.entry_id, refresh_now=True)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert reader.count("index.json") > before
    assert "refresh_now" not in result["data"]
    await _finish(hass, entry.entry_id)


async def test_clear_deletes_the_saved_files_and_reads_them_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    reader = CountingReader(use_store())
    use_store(reader)
    freezer.move_to(NOON)
    entry = await _setup(hass)
    before = reader.count("1.json")

    result = await _save(hass, entry.entry_id, clear_cache=True)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert reader.count("1.json") > before  # the plan's file came from the store, not the cache
    assert "clear_cache" not in result["data"]
    await _finish(hass, entry.entry_id)


async def test_nothing_is_read_again_when_neither_is_asked(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    reader = CountingReader(use_store())
    use_store(reader)
    freezer.move_to(NOON)
    entry = await _setup(hass)
    before = len(reader.reads)

    await _save(hass, entry.entry_id)

    assert len(reader.reads) == before
    await _finish(hass, entry.entry_id)


async def test_clear_is_refused_while_the_store_is_unreachable(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, use_store: Callable[..., Path]
) -> None:
    reader = CountingReader(use_store())
    use_store(reader)
    freezer.move_to(NOON)
    entry = await _setup(hass)
    reader.down = True
    await entry.runtime_data.async_refresh_store()
    assert entry.runtime_data.access.offline

    result = await _save(hass, entry.entry_id, clear_cache=True)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "clear_while_offline"}
    assert hass.states.get("sensor.utility_tariff_import_price").state == "0.3"
    await _finish(hass, entry.entry_id)
