# Copied from the tariff store by scripts/copy_tariffstore.py. Do not edit here.
"""price_timeline: prices across a revision, from a feed, how far they are known, and the helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.utility_tariffs.lib.tariff import (
    PriceSeries,
    Revision,
    feed_of,
    known_until,
    parse_definition,
    price_curve,
    price_timeline,
    series_curve,
    series_factor,
    series_names,
    series_runs,
)
from tests.lib.tariff.example_definition import example_document
from tests.lib.tariff.test_price_series import day, dynamic_document

D = Decimal
UTC = timezone.utc
DUBLIN = ZoneInfo("Europe/Dublin")
START = datetime(2026, 11, 16, tzinfo=UTC)  # Dublin is on UTC in November


def _series(prices: list[str], start: datetime = START) -> PriceSeries:
    return PriceSeries(start, timedelta(minutes=30), tuple(D(p) for p in prices))


def _dynamic():  # type: ignore[no-untyped-def]
    return parse_definition(dynamic_document())


def _dearer(percent: str = "10"):  # type: ignore[no-untyped-def]
    doc: dict[str, Any] = example_document()
    doc["revision"], doc["supersedes"], doc["effective_from"] = 2, 1, "2026-11-18"
    doc["import"]["base"]["price"] = str(D("0.365") * (1 + D(percent) / 100))
    doc.pop("checks")
    doc["completeness"] = "partial"
    return parse_definition(doc)


def test_the_series_a_tariff_names_and_the_feed_it_stands_for() -> None:
    assert series_names(_dynamic()) == ("agile",)
    assert series_names(parse_definition(example_document())) == ()
    assert feed_of("octopus_agile") == "octopus-agile"


def test_runs_split_at_a_gap_and_are_earliest_first() -> None:
    runs = series_runs([day("2026-11-19", ["0.1"] * 48), day("2026-11-16", ["0.1"] * 48),
                        day("2026-11-17", ["0.2"] * 48)])
    assert [len(run.prices) for run in runs] == [96, 48]
    assert runs[1].start == datetime(2026, 11, 19, tzinfo=UTC)
    assert series_runs([]) == []


def test_the_factor_is_what_the_bill_does_to_a_series_price() -> None:
    assert series_factor(_dynamic(), "agile") == D("1.05")  # the example adds 5% VAT


def test_a_feed_slot_carries_the_published_price_through_the_bill() -> None:
    slots = series_curve(_dynamic(), _series(["0.10", "0.20", "0.20", "0.30"]), START,
                         START + timedelta(hours=2))
    assert [(s.import_price, s.source) for s in slots] == [
        (D("0.105"), "published"), (D("0.21"), "published"), (D("0.315"), "published")]
    assert slots[1].end - slots[1].start == timedelta(hours=1)  # equal neighbours are joined
    assert slots[0].export_price == D(0)  # this bill tree pays nothing for export


def test_feed_slots_stop_where_the_series_stops_and_are_cut_to_the_range() -> None:
    series = _series(["0.10"] * 4)  # two hours
    slots = series_curve(_dynamic(), series, START + timedelta(minutes=45),
                         START + timedelta(hours=5))
    assert slots[0].start == START + timedelta(minutes=45)
    assert slots[-1].end == START + timedelta(hours=2)
    assert series_curve(_dynamic(), series, START + timedelta(hours=3),
                        START + timedelta(hours=4)) == ()


def test_a_range_over_a_revision_uses_each_revisions_prices() -> None:
    first, second = parse_definition(example_document()), _dearer()
    start = datetime(2026, 11, 17, 12, tzinfo=DUBLIN)
    end = datetime(2026, 11, 18, 12, tzinfo=DUBLIN)
    slots = price_timeline(
        [Revision(date(2026, 11, 1), first), Revision(date(2026, 11, 18), second)], start, end)
    assert slots[0].start == start and slots[-1].end == end
    boundary = datetime(2026, 11, 18, tzinfo=DUBLIN)
    before = [s for s in slots if s.start < boundary]
    after = [s for s in slots if s.start >= boundary]
    assert before[-1].end == boundary
    assert {s.import_price for s in before if s.import_band == "Day"} == {
        price_curve(first, start, start + timedelta(hours=1))[0].import_price}
    day_after = next(s for s in after if s.import_band == "Day")
    assert day_after.import_price > before[0].import_price


def test_a_revision_outside_the_range_is_ignored() -> None:
    first, second = parse_definition(example_document()), _dearer()
    start = datetime(2026, 11, 17, tzinfo=DUBLIN)
    end = datetime(2026, 11, 17, 6, tzinfo=DUBLIN)
    revisions = [Revision(date(2026, 11, 1), first), Revision(date(2026, 11, 18), second)]
    assert price_timeline(revisions, start, end) == price_curve(first, start, end)
    late = [Revision(date(2026, 11, 1), first), Revision(date(2026, 11, 16), second)]
    assert price_timeline(late, start, end) == price_curve(second, start, end)


def test_a_feed_tariff_in_a_timeline_has_prices_only_where_published() -> None:
    runs = {"agile": [_series(["0.10"] * 48), _series(["0.30"] * 48, START + timedelta(days=2))]}
    slots = price_timeline([Revision(date(2026, 11, 1), _dynamic())], START,
                           START + timedelta(days=4), runs)
    assert [(s.start, s.end) for s in slots] == [
        (START, START + timedelta(days=1)),
        (START + timedelta(days=2), START + timedelta(days=3))]
    assert known_until(slots, START) == START + timedelta(days=1)
    assert known_until(slots, START + timedelta(days=2)) == START + timedelta(days=3)
    assert known_until(slots, START + timedelta(days=1)) is None
    assert price_timeline([Revision(date(2026, 11, 1), _dynamic())], START,
                          START + timedelta(days=1)) == ()


def test_known_until_follows_slots_that_meet_and_stops_at_a_break() -> None:
    first, second = parse_definition(example_document()), _dearer()
    revisions = [Revision(date(2026, 11, 1), first), Revision(date(2026, 11, 18), second)]
    start, end = datetime(2026, 11, 17, tzinfo=DUBLIN), datetime(2026, 11, 20, tzinfo=DUBLIN)
    assert known_until(price_timeline(revisions, start, end), start) == end


def test_bad_ranges_and_more_than_one_series_are_refused() -> None:
    with pytest.raises(ValueError, match="at least one revision"):
        price_timeline([], START, START + timedelta(days=1))
    with pytest.raises(ValueError, match="end must be after start"):
        price_timeline([Revision(date(2026, 11, 1), _dynamic())], START, START)
    doc = dynamic_document()
    doc["bill"]["total"]["of"]["of"]["second"] = {"kind": "series_energy", "series": "other"}
    with pytest.raises(ValueError, match="more than one price series"):
        price_timeline([Revision(date(2026, 11, 1), parse_definition(doc))], START,
                       START + timedelta(days=1), {})


def test_the_tree_walk_reaches_into_lists_and_ignores_text() -> None:
    from custom_components.utility_tariffs.lib.tariff.price_series import _walk
    assert list(_walk(["text", (1, 2), {"a": "b"}])) == []
