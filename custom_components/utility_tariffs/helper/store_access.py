"""
store_access.py - reads the open tariff store for the screens and the update timer.

The store client (`utility_tariffs_lib.tariffstore.AsyncStore`) is async and takes the web session
it reads through, so nothing here blocks the event loop and no thread is involved:

- Files are fetched through Home Assistant's shared web session, so the host's proxy and
  certificate settings apply.
- What was read is kept in a folder under `.storage`, named by the caller, so a tariff in use is
  downloaded once and can be read again with no network. The folder's file work runs in a worker
  thread inside the cache.
- Calls take turns, one at a time per install, because the daily update check, the plan ranking
  and a setup screen can ask for the same file together and share one cache folder.

Only static file paths are requested. Nothing about the install, its place or its usage is sent.
Home Assistant imports are lazy, so the unit tests do not need them.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import weakref
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, TypeVar

from utility_tariffs_lib.tariff import TariffDefinition, parse_definition
from utility_tariffs_lib.tariffstore import (
    AsyncFolderCache,
    AsyncPriceStore,
    AsyncStore,
    StoreError,
    session_reader,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOG = logging.getLogger(__name__)
_T = TypeVar("_T")
REQUEST_TIMEOUT_S = 30


def _home_assistant_session(hass: HomeAssistant) -> Any:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    return async_get_clientsession(hass)


def _reader(
    hass: HomeAssistant,
    base_url: str,
    get_session: Callable[[HomeAssistant], Any] | None = None,
) -> Callable[[str], Awaitable[bytes]]:
    """A reader that fetches through Home Assistant's web session. Raises ValueError unless the
    store is https. A failed request is an OSError to the client, which answers from its cache."""
    from aiohttp import ClientError

    session = (get_session or _home_assistant_session)(hass)
    return session_reader(session, base_url, timeout=REQUEST_TIMEOUT_S, errors=(ClientError,))


def _empty_folder(folder: Path | None) -> None:
    """Delete what the cache holds. The cache makes its folder again on the next write."""
    if folder is not None and folder.exists():
        shutil.rmtree(folder)


_LOCKS: weakref.WeakKeyDictionary[Any, asyncio.Lock] = weakref.WeakKeyDictionary()


def _lock_of(hass: Any) -> asyncio.Lock:
    if hass not in _LOCKS:
        _LOCKS[hass] = asyncio.Lock()
    return _LOCKS[hass]


class TariffStoreAccess:
    """The store as the screens use it: awaitable calls that never block the event loop."""

    def __init__(
        self, hass: HomeAssistant, store: AsyncStore, folder: Path | None = None
    ) -> None:
        self._hass = hass
        self._store = store
        self._folder = folder

    @classmethod
    def for_home_assistant(cls, hass: HomeAssistant, base_url: str, cache_folder: str) -> Self:
        """The store at *base_url*, cached in a folder of that name under `.storage`."""
        folder = Path(hass.config.path(".storage", cache_folder))
        store = AsyncStore(_reader(hass, base_url), AsyncFolderCache(folder))
        return cls(hass, store, folder)

    @property
    def offline(self) -> bool:
        """True when the last read was answered from the cache because the store was unreachable."""
        return self._store.offline

    async def _run(self, call: Callable[[], Awaitable[_T]]) -> _T:
        async with _lock_of(self._hass):
            return await call()

    async def async_refresh(self) -> None:
        """Read the countries index again on the next call, whatever its age."""
        self._store.refresh()

    async def async_clear_cache(self) -> None:
        """Delete every saved file, and read the store afresh on the next call."""
        async with _lock_of(self._hass):
            await self._hass.async_add_executor_job(_empty_folder, self._folder)
            self._store.refresh()

    async def async_countries(self) -> dict[str, dict[str, Any]]:
        return await self._run(self._store.countries)

    async def async_providers(self, country: str) -> dict[str, str]:
        return await self._run(lambda: self._store.providers(country))

    async def async_tariffs(self, country: str, provider: str, on: date) -> dict[str, str]:
        return await self._run(lambda: self._store.tariffs(country, provider, on=on))

    async def async_areas(
        self, country: str, provider: str, tariff: str, on: date
    ) -> dict[str, str]:
        return await self._run(lambda: self._store.areas(country, provider, tariff, on))

    async def async_is_holiday(
        self, country: str, region: str | None = None
    ) -> Callable[[date], bool]:
        """Whether a day is a public holiday there. Raises StoreError when none are held."""
        return await self._run(lambda: self._store.is_holiday(country, region))

    async def async_revision_starts(  # noqa: PLR0913
        self, country: str, provider: str, tariff: str, on: date, until: date
    ) -> list[tuple[date, int]]:
        """(first day, revision) of each revision that starts after *on*, up to *until*."""
        return await self._run(
            lambda: self._store.revision_starts(country, provider, tariff, on, until)
        )

    async def async_definition(  # noqa: PLR0913
        self,
        country: str,
        provider: str,
        tariff: str,
        on: date,
        area: str = "all",
        export: str | None = None,
    ) -> TariffDefinition:
        """The checked, parsed definition of one area of a tariff on a day."""
        document = await self._run(
            lambda: self._store.definition(
                country, provider, tariff, on, area=area, export=export
            )
        )
        return parse_definition(document)


class PriceStoreAccess:
    """The dynamic prices as the coordinator uses them, read one call at a time."""

    def __init__(
        self, hass: HomeAssistant, store: AsyncPriceStore, folder: Path | None = None
    ) -> None:
        self._hass = hass
        self._store = store
        self._folder = folder

    @classmethod
    def for_home_assistant(cls, hass: HomeAssistant, base_url: str, cache_folder: str) -> Self:
        folder = Path(hass.config.path(".storage", cache_folder))
        store = AsyncPriceStore(_reader(hass, base_url), AsyncFolderCache(folder))
        return cls(hass, store, folder)

    async def async_clear_cache(self) -> None:
        """Delete every saved price day. They are fetched again on the next read."""
        async with _lock_of(self._hass):
            await self._hass.async_add_executor_job(_empty_folder, self._folder)

    async def async_days(  # noqa: PLR0913
        self, country: str, feed: str, area: str, first: date, last: date
    ) -> tuple[list[dict[str, Any]], list[date]]:
        """(day files held, days missing) from *first* to *last*."""
        async with _lock_of(self._hass):
            return await self._store.days(country, feed, area, first, last)


__all__ = ["PriceStoreAccess", "StoreError", "TariffStoreAccess"]
