"""The tariff store as the screens use it: awaitable, cached, read through the web session."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from utility_tariffs_lib.tariffstore import (
    AsyncFolderCache,
    AsyncStore,
    StoreError,
    folder_reader,
)

from custom_components.utility_tariffs.helper import store_access
from custom_components.utility_tariffs.helper.store_access import (
    PriceStoreAccess,
    TariffStoreAccess,
    _home_assistant_session,
    _reader,
)
from tests.helpers import async_reader
from tests.support.building import build_store
from tests.support.fixtures import write_store

DAY = date(2026, 11, 12)


class FakeHass:
    def __init__(self, base: Path | None = None) -> None:
        self.config = SimpleNamespace(path=lambda *parts: str((base or Path("/x")).joinpath(*parts)))


@pytest.fixture
def tariffs(tmp_path: Path) -> Path:
    folder = write_store(tmp_path)
    build_store(folder)
    return folder


def _access(tariffs: Path, cache: Path) -> TariffStoreAccess:
    store = AsyncStore(async_reader(folder_reader(tariffs)), AsyncFolderCache(cache))
    return TariffStoreAccess(FakeHass(), store)  # type: ignore[arg-type]


async def test_lists_countries_providers_tariffs_and_areas(tariffs: Path, tmp_path: Path) -> None:
    access = _access(tariffs, tmp_path / "cache")
    assert "IE" in await access.async_countries()
    providers = await access.async_providers("IE")
    assert list(providers) == ["p"]
    tariff_ids = await access.async_tariffs("IE", "p", DAY)
    assert list(tariff_ids) == ["plan"]
    assert list(await access.async_areas("IE", "p", "plan", DAY)) == ["rural", "urban"]


async def test_the_definition_is_parsed_and_priced_from_the_store(
    tariffs: Path, tmp_path: Path
) -> None:
    access = _access(tariffs, tmp_path / "cache")
    definition = await access.async_definition("IE", "p", "plan", DAY, "urban")
    assert definition.country == "IE"
    assert definition.currency == "EUR"


async def test_a_tariff_already_read_is_still_readable_with_no_network(
    tariffs: Path, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    await _access(tariffs, cache).async_definition("IE", "p", "plan", DAY, "urban")

    async def unreachable(path: str) -> bytes:
        raise OSError("no network")

    offline = TariffStoreAccess(
        FakeHass(),  # type: ignore[arg-type]
        AsyncStore(unreachable, AsyncFolderCache(cache), max_age=0),
    )
    definition = await offline.async_definition("IE", "p", "plan", DAY, "urban")
    assert definition.country == "IE"
    assert offline.offline


async def test_a_store_never_read_and_unreachable_is_an_error(tmp_path: Path) -> None:
    async def unreachable(path: str) -> bytes:
        raise OSError("no network")

    access = TariffStoreAccess(
        FakeHass(),  # type: ignore[arg-type]
        AsyncStore(unreachable, AsyncFolderCache(tmp_path / "cache")),
    )
    with pytest.raises(StoreError):
        await access.async_countries()


async def test_holidays_and_revision_starts_come_from_the_held_files(
    tariffs: Path, tmp_path: Path
) -> None:
    access = _access(tariffs, tmp_path / "cache")
    assert await access.async_revision_starts("IE", "p", "plan", DAY, date(2027, 1, 1)) == []
    with pytest.raises(StoreError):
        await access.async_is_holiday("IE")


async def test_a_refresh_reads_the_countries_index_again(tariffs: Path, tmp_path: Path) -> None:
    access = _access(tariffs, tmp_path / "cache")
    await access.async_countries()
    await access.async_refresh()
    assert "IE" in await access.async_countries()


def test_the_reader_refuses_a_store_that_is_not_https() -> None:
    with pytest.raises(ValueError, match="https"):
        _reader(FakeHass(), "http://example.invalid/tariffs", lambda _hass: object())  # type: ignore[arg-type]


async def test_the_reader_fetches_through_the_session_it_is_given() -> None:
    seen: list[str] = []

    class Reply:
        def raise_for_status(self) -> None:
            return None

        async def read(self) -> bytes:
            return b"{}"

        async def __aenter__(self) -> Reply:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

    class Session:
        def get(self, url: str, **kwargs: Any) -> Reply:
            seen.append(url)
            return Reply()

    read = _reader(FakeHass(), "https://example.invalid/tariffs/", lambda _hass: Session())  # type: ignore[arg-type]
    assert await read("index.json") == b"{}"
    assert seen == ["https://example.invalid/tariffs/index.json"]


async def test_a_network_error_becomes_an_os_error_for_the_client() -> None:
    from aiohttp import ClientConnectionError

    class Session:
        def get(self, url: str, **kwargs: Any) -> Any:
            raise ClientConnectionError("down")

    read = _reader(FakeHass(), "https://example.invalid/t", lambda _hass: Session())  # type: ignore[arg-type]
    with pytest.raises(OSError, match="down"):
        await read("index.json")


async def test_the_home_assistant_access_caches_in_the_named_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store_access, "_home_assistant_session", lambda _hass: object())
    hass = FakeHass(tmp_path)
    access = TariffStoreAccess.for_home_assistant(
        hass,  # type: ignore[arg-type]
        "https://example.invalid/tariffs",
        "example_store",
    )
    assert access.offline is False
    assert isinstance(
        PriceStoreAccess.for_home_assistant(
            hass,  # type: ignore[arg-type]
            "https://example.invalid/prices",
            "example_prices",
        ),
        PriceStoreAccess,
    )
    with pytest.raises(ValueError, match="https"):
        TariffStoreAccess.for_home_assistant(
            hass,  # type: ignore[arg-type]
            "http://example.invalid/tariffs",
            "example_store",
        )


def test_the_default_session_is_homes_assistants_shared_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from types import ModuleType

    module = ModuleType("homeassistant.helpers.aiohttp_client")
    module.async_get_clientsession = lambda hass: ("session", hass)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.aiohttp_client", module)

    assert _home_assistant_session("hass") == ("session", "hass")  # type: ignore[arg-type]


async def test_two_readers_of_one_install_never_read_the_store_at_the_same_time() -> None:
    """The update check and the plan ranking share one cache folder, so their reads take turns."""
    running = 0
    overlap = 0

    class Slow:
        offline = False

        async def countries(self) -> dict[str, Any]:
            nonlocal running, overlap
            running += 1
            overlap = max(overlap, running)
            await asyncio.sleep(0.01)
            running -= 1
            return {}

    hass = FakeHass()
    one = TariffStoreAccess(hass, Slow())  # type: ignore[arg-type]
    two = TariffStoreAccess(hass, Slow())  # type: ignore[arg-type]
    await asyncio.gather(one.async_countries(), two.async_countries(), one.async_countries())
    assert overlap == 1
