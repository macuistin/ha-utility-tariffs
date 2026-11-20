"""Shared paths for the unit tests, so no test depends on the working directory."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "custom_components" / "utility_tariffs"


def async_reader(read: Callable[[str], bytes]) -> Callable[[str], Awaitable[bytes]]:
    """A blocking test reader as the awaitable one the async store client takes."""

    async def read_async(path: str) -> bytes:
        return read(path)

    return read_async


def without_bands(ids: dict[str, str]) -> dict[str, str]:
    """The entities of a followed plan except its band price sensors, which follow its bands."""
    return {uid: entity for uid, entity in ids.items() if "_band_price_" not in uid}
