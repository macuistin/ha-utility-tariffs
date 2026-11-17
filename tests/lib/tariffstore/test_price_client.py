# Copied from the tariff store by scripts/copy_tariffstore.py. Do not edit here.
"""The price client: day files from the prices branch, checked, kept and never guessed."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from custom_components.utility_tariffs.lib.tariffstore import FolderCache, PriceStore, StoreError, prices


def day_file(day: str, feed: str = "octopus-agile", area: str = "c", count: int = 48) -> bytes:
    doc = {"schema": 1, "feed": feed, "area": area, "date": day, "timezone": "Europe/London",
           "interval_minutes": 30, "prices": ["0.2"] * count}
    return prices.dumps_day(doc).encode()


class Reads(unittest.TestCase):
    def setUp(self) -> None:
        self.files = {
            "gb/octopus-agile/c/2026/11/16.json": day_file("2026-11-16"),
            "gb/octopus-agile/c/2026/11/17.json": day_file("2026-11-17"),
            "gb/octopus-agile/c/index.json": json.dumps(
                {"schema": 1, "feed": "octopus-agile", "area": "c", "latest": "2026-11-17",
                 "months": {}}).encode(),
        }
        self.reads: list[str] = []

        def read(path: str) -> bytes:
            self.reads.append(path)
            try:
                return self.files[path]
            except KeyError:
                raise OSError("404") from None
        self.store = PriceStore(read)

    def test_a_day_is_read_checked_and_kept(self) -> None:
        doc = self.store.day("GB", "octopus-agile", "c", date(2026, 11, 16))
        self.assertEqual(len(doc["prices"]), 48)
        self.store.day("GB", "octopus-agile", "c", date(2026, 11, 16))
        self.assertEqual(self.reads, ["gb/octopus-agile/c/2026/11/16.json"])

    def test_days_reports_the_days_it_could_not_read(self) -> None:
        held, missing = self.store.days("GB", "octopus-agile", "c", date(2026, 11, 16),
                                        date(2026, 11, 18))
        self.assertEqual([d["date"] for d in held], ["2026-11-16", "2026-11-17"])
        self.assertEqual(missing, [date(2026, 11, 18)])

    def test_the_latest_day_is_always_read_afresh(self) -> None:
        self.assertEqual(self.store.latest("GB", "octopus-agile", "c"), date(2026, 11, 17))
        self.store.latest("GB", "octopus-agile", "c")
        self.assertEqual(self.reads.count("gb/octopus-agile/c/index.json"), 2)
        self.files["gb/octopus-agile/c/index.json"] = json.dumps({"latest": None}).encode()
        self.assertIsNone(self.store.latest("GB", "octopus-agile", "c"))
        self.files["gb/octopus-agile/c/index.json"] = json.dumps({"latest": "soon"}).encode()
        with self.assertRaisesRegex(StoreError, "latest is not a date"):
            self.store.latest("GB", "octopus-agile", "c")

    def test_a_file_that_is_not_valid_is_refused(self) -> None:
        self.files["gb/octopus-agile/c/2026/11/16.json"] = day_file("2026-11-16", count=47)
        with self.assertRaisesRegex(StoreError, "has 48 prices, not 47"):
            self.store.day("GB", "octopus-agile", "c", date(2026, 11, 16))

    def test_a_file_for_another_area_or_day_is_refused(self) -> None:
        self.files["gb/octopus-agile/c/2026/11/16.json"] = day_file("2026-11-16", area="d")
        with self.assertRaisesRegex(StoreError, "another feed, area or day"):
            self.store.day("GB", "octopus-agile", "c", date(2026, 11, 16))
        self.files["gb/octopus-agile/c/2026/11/17.json"] = day_file("2026-11-16")
        with self.assertRaisesRegex(StoreError, "another feed, area or day"):
            self.store.day("GB", "octopus-agile", "c", date(2026, 11, 17))

    def test_a_file_that_is_not_json_is_refused(self) -> None:
        for body in (b"<html>", b"[1]"):
            self.files["gb/octopus-agile/c/2026/11/16.json"] = body
            with self.assertRaisesRegex(StoreError, "not JSON|not a JSON object"):
                self.store.day("GB", "octopus-agile", "c", date(2026, 11, 16))

    def test_a_day_that_is_held_is_used_with_no_network(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            first = PriceStore(self.store._read, FolderCache(folder))
            first.day("GB", "octopus-agile", "c", date(2026, 11, 16))

            def down(path: str) -> bytes:
                raise OSError("offline")
            second = PriceStore(down, FolderCache(Path(folder)))
            self.assertEqual(
                second.day("GB", "octopus-agile", "c", date(2026, 11, 16))["date"], "2026-11-16")
            with self.assertRaises(StoreError):
                second.day("GB", "octopus-agile", "c", date(2026, 11, 17))
