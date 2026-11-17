"""Read dynamic price day files from the `prices` branch. Standard library only.

A `PriceStore` is given one function, `read(path) -> bytes`, like `Store`, but for the prices
folder (the root of the `prices` branch). Each day file is checked with `validate_day` before it is
trusted, and must say the country feed, area and date it was asked for. A published day is never
changed, so a day that is held is never fetched again. A day that cannot be read is reported as
missing and never guessed.

The feed index lists a checksum for each month, not for each day, so it is not needed to read one
day. A client that wants to know the newest day published reads `latest()`.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from .client import FolderCache, MemoryCache, StoreError, _safe
from .prices import day_path, index_path, validate_day

Doc = dict[str, Any]


class PriceStore:
    """Dynamic prices, read through `read` and kept in `cache`."""

    def __init__(self, read: Callable[[str], bytes],
                 cache: MemoryCache | FolderCache | None = None) -> None:
        self._read = read
        self._cache = cache if cache is not None else MemoryCache()

    def _parsed(self, path: str, raw: bytes) -> Doc:
        try:
            doc = json.loads(raw)
        except ValueError as error:
            raise StoreError(f"{path}: not JSON ({error})") from error
        if not isinstance(doc, dict):
            raise StoreError(f"{path}: not a JSON object")
        return doc

    def _fetch(self, path: str) -> bytes:
        try:
            return self._read(_safe(path))
        except OSError as error:
            raise StoreError(f"{path}: cannot be read ({error})") from error

    def latest(self, country: str, feed: str, area: str) -> date | None:
        """The newest day the feed index lists, or None when it holds no day. Always read afresh."""
        path = index_path(country, feed, area)
        doc = self._parsed(path, self._fetch(path))
        latest = doc.get("latest")
        try:
            return date.fromisoformat(latest) if latest else None
        except (TypeError, ValueError):
            raise StoreError(f"{path}: latest is not a date") from None

    def day(self, country: str, feed: str, area: str, day: date) -> Doc:
        """The valid day file for one day. Raises `StoreError` when it cannot be read or checked."""
        path = day_path(country, feed, area, day)
        held = self._cache.get(path)
        raw = held if held is not None else self._fetch(path)
        doc = self._parsed(path, raw)
        problems = validate_day(doc)
        if not problems and (doc["feed"], doc["area"], doc["date"]) != (
                feed, area, day.isoformat()):
            problems = ["the file is for another feed, area or day"]
        if problems:
            raise StoreError(f"{path}: " + "; ".join(problems))
        if held is None:
            self._cache.put(path, raw)
        return doc

    def days(self, country: str, feed: str, area: str, first: date,  # noqa: PLR0913
             last: date) -> tuple[list[Doc], list[date]]:
        """(day files held, days missing) from `first` to `last`, both included, earliest first.
        A day that cannot be read or is refused is missing."""
        held: list[Doc] = []
        missing: list[date] = []
        day = first
        while day <= last:
            try:
                held.append(self.day(country, feed, area, day))
            except StoreError:
                missing.append(day)
            day += timedelta(days=1)
        return held, missing
