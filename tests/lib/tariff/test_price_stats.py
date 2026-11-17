# Copied from the tariff store by scripts/copy_tariffstore.py. Do not edit here.
"""The lowest, highest and average price of a range, and the rating of a price."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from custom_components.utility_tariffs.lib.tariff import PriceSlot, price_rating, price_stats
from custom_components.utility_tariffs.lib.tariff.price_stats import RATINGS, PriceStats

D = Decimal
MIDNIGHT = datetime(2026, 6, 1, 0, 0, tzinfo=ZoneInfo("Europe/Dublin"))


def _slot(minutes_from: int, minutes_to: int, price: str, export: str = "0.05") -> PriceSlot:
    return PriceSlot(
        MIDNIGHT + timedelta(minutes=minutes_from),
        MIDNIGHT + timedelta(minutes=minutes_to),
        "b", "x", D(price), D(export),
    )


DAY = (MIDNIGHT, MIDNIGHT + timedelta(days=1))


def test_the_average_is_weighted_by_time() -> None:
    slots = [_slot(0, 360, "0.10"), _slot(360, 1440, "0.30")]
    stats = price_stats(slots, *DAY)
    assert stats == PriceStats(D("0.10"), D("0.30"), D("0.25"), True)


def test_export_prices_can_be_asked_for() -> None:
    slots = [_slot(0, 720, "0.10", "0.02"), _slot(720, 1440, "0.30", "0.06")]
    stats = price_stats(slots, *DAY, flow="export")
    assert stats is not None and (stats.lowest, stats.highest) == (D("0.02"), D("0.06"))


def test_slots_are_cut_at_the_range() -> None:
    slots = [_slot(0, 600, "0.10"), _slot(600, 1440, "0.90")]
    stats = price_stats(slots, MIDNIGHT, MIDNIGHT + timedelta(hours=12))
    assert stats is not None and stats.highest == D("0.90") and stats.complete


def test_a_range_the_prices_do_not_cover_is_marked_incomplete() -> None:
    stats = price_stats([_slot(0, 720, "0.10")], *DAY)
    assert stats is not None and stats.complete is False and stats.average == D("0.10")


def test_a_range_with_no_prices_has_no_statistics() -> None:
    assert price_stats([_slot(0, 60, "0.10")], MIDNIGHT + timedelta(days=2),
                       MIDNIGHT + timedelta(days=3)) is None
    assert price_stats([], *DAY) is None


def test_an_empty_range_is_refused() -> None:
    with pytest.raises(ValueError, match="after start"):
        price_stats([], MIDNIGHT, MIDNIGHT)


@pytest.mark.parametrize(
    ("price", "rating"),
    [("0.10", "very_low"), ("0.1799", "very_low"), ("0.18", "low"), ("0.20", "low"), ("0.30", "normal"),
     ("0.40", "high"), ("0.50", "very_high"), ("0.60", "very_high"), ("0.05", "very_low")],
)
def test_a_price_is_rated_by_its_place_in_the_range(price: str, rating: str) -> None:
    stats = PriceStats(D("0.10"), D("0.50"), D("0.30"), True)
    assert price_rating(D(price), stats) == rating


def test_a_single_price_rates_as_normal() -> None:
    stats = PriceStats(D("0.20"), D("0.20"), D("0.20"), True)
    assert price_rating(D("0.20"), stats) == "normal"


def test_there_are_five_ratings_from_low_to_high() -> None:
    assert RATINGS == ("very_low", "low", "normal", "high", "very_high")


# Percentiles: what low, middle and high look like.

from custom_components.utility_tariffs.lib.tariff import HistoryPercentiles, history_percentiles, price_level, price_percentiles  # noqa: E402


def _hourly(prices: list[str], start: datetime = MIDNIGHT) -> list[PriceSlot]:
    return [
        PriceSlot(start + timedelta(hours=i), start + timedelta(hours=i + 1), "b", "x", D(p), D("0"))
        for i, p in enumerate(prices)
    ]


def test_percentiles_are_weighted_by_time_and_take_a_price_that_exists() -> None:
    slots = _hourly(["0.10"] * 6 + ["0.20"] * 12 + ["0.50"] * 6)
    assert price_percentiles(slots, *DAY) == {10: D("0.10"), 50: D("0.20"), 90: D("0.50")}
    # a long cheap price counts for its whole length, not once
    long_cheap = [_slot(0, 1080, "0.10"), _slot(1080, 1440, "0.90")]
    assert price_percentiles(long_cheap, *DAY, points=(50, 75, 90)) == {
        50: D("0.10"), 75: D("0.10"), 90: D("0.90")}


def test_percentiles_wait_for_six_hours_of_prices() -> None:
    assert price_percentiles(_hourly(["0.1"] * 5), *DAY) is None
    assert price_percentiles(_hourly(["0.1"] * 6), *DAY) is not None
    assert price_percentiles([], *DAY) is None


def test_percentiles_can_be_asked_for_export_and_refuse_a_bad_range() -> None:
    slots = [_slot(0, 720, "0.10", "0.02"), _slot(720, 1440, "0.30", "0.06")]
    assert price_percentiles(slots, *DAY, flow="export", points=(50,)) == {50: D("0.02")}
    with pytest.raises(ValueError, match="end must be after start"):
        price_percentiles(slots, DAY[1], DAY[0])


def _days(count: int, price: str = "0.20", expensive_evening: str = "0.40") -> list[PriceSlot]:
    """Half-hourly prices for *count* days before MIDNIGHT, dearer from 16:00 to 19:00."""
    slots = []
    start = MIDNIGHT - timedelta(days=count)
    for index in range(count * 48):
        begin = start + timedelta(minutes=30 * index)
        evening = 16 <= begin.hour < 19
        slots.append(PriceSlot(begin, begin + timedelta(minutes=30), "b", "x",
                               D(expensive_evening if evening else price), D("0")))
    return slots


def test_history_looks_at_the_same_part_of_the_day_on_each_past_day() -> None:
    moment = MIDNIGHT.replace(hour=17)  # 15:00 to 19:00 of each day is compared
    found = history_percentiles(_days(10), moment)
    assert isinstance(found, HistoryPercentiles) and found.days == 10
    assert found.points == {10: D("0.20"), 50: D("0.40"), 90: D("0.40")}
    overnight = history_percentiles(_days(10), MIDNIGHT.replace(hour=3))
    assert overnight is not None and set(overnight.points.values()) == {D("0.20")}


def test_history_waits_for_seven_whole_days() -> None:
    moment = MIDNIGHT.replace(hour=12)
    assert history_percentiles(_days(6), moment) is None
    seen = history_percentiles(_days(7), moment)
    assert seen is not None and seen.days == 7
    assert history_percentiles([], moment) is None


def test_history_is_capped_at_the_look_back() -> None:
    found = history_percentiles(_days(40), MIDNIGHT.replace(hour=12))
    assert found is not None and found.days == 28
    short = history_percentiles(_days(40), MIDNIGHT.replace(hour=12), look_back=10)
    assert short is not None and short.days == 10


def test_history_keeps_the_time_of_day_across_a_clock_change() -> None:
    zone = ZoneInfo("Europe/Dublin")
    moment = datetime(2026, 10, 28, 12, tzinfo=zone)  # the clocks went back on 25 October
    slots = []
    cursor = datetime(2026, 10, 1, tzinfo=zone)
    while cursor < moment:
        end = (cursor.astimezone(ZoneInfo("UTC")) + timedelta(minutes=30)).astimezone(zone)
        slots.append(PriceSlot(cursor, end, "b", "x", D("0.5") if cursor.hour == 12 else D("0.1"),
                               D("0")))
        cursor = end
    found = history_percentiles(slots, moment)
    assert found is not None and found.days == 27
    assert found.points[90] == D("0.5") and found.points[10] == D("0.1")


def test_a_level_says_low_mid_or_high() -> None:
    points = {10: D("0.10"), 50: D("0.20"), 90: D("0.40")}
    assert price_level(D("0.05"), points) == "low"
    assert price_level(D("0.10"), points) == "low"
    assert price_level(D("0.25"), points) == "mid"
    assert price_level(D("0.40"), points) == "high"
    assert price_level(D("0.30"), {10: D("0.2"), 90: D("0.2")}) == "mid"  # no spread
    assert price_level(D("0.30"), {50: D("0.2")}) == "mid"


def test_the_next_cheap_slot_is_the_one_in_force_or_the_first_after() -> None:
    from custom_components.utility_tariffs.lib.tariff import next_at_or_below

    slots = _hourly(["0.30", "0.10", "0.30", "0.05", "0.30"])
    noon = MIDNIGHT
    assert next_at_or_below(slots, noon, D("0.10")).start == MIDNIGHT + timedelta(hours=1)
    # in the middle of a cheap slot, that slot is still the answer
    assert next_at_or_below(slots, noon + timedelta(minutes=90), D("0.10")).start == \
        MIDNIGHT + timedelta(hours=1)
    assert next_at_or_below(slots, noon + timedelta(hours=2), D("0.10")).start == \
        MIDNIGHT + timedelta(hours=3)
    assert next_at_or_below(slots, noon + timedelta(hours=4), D("0.10")) is None
    assert next_at_or_below(slots, noon, D("0.01")) is None
    assert next_at_or_below(list(reversed(slots)), noon, D("0.30")).start == MIDNIGHT
    export = [_slot(0, 60, "0.5", "0.02"), _slot(60, 120, "0.5", "0.09")]
    assert next_at_or_below(export, MIDNIGHT, D("0.05"), flow="export").start == MIDNIGHT


def test_the_low_and_high_percentiles_can_be_chosen() -> None:
    points = {25: D("0.15"), 75: D("0.35"), 10: D("0.10"), 90: D("0.40")}
    assert price_level(D("0.20"), points) == "mid"
    assert price_level(D("0.20"), points, low=25, high=75) == "mid"
    assert price_level(D("0.15"), points, low=25, high=75) == "low"
    assert price_level(D("0.36"), points, low=25, high=75) == "high"
    assert price_level(D("0.01"), points, low=30, high=75) == "mid"  # 30 was not worked out
