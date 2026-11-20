"""Reading the user's energy meters: units, bad readings and the rise between two readings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import State

from custom_components.utility_tariffs.meter import RiseTracker, kwh_of

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _state(value: str, unit: str | None = "kWh") -> State:
    return State("sensor.meter", value, {"unit_of_measurement": unit} if unit else {})


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (_state("12.5"), 12.5),
        (_state("1500", "Wh"), 1.5),
        (_state("0.002", "MWh"), 2.0),
        (_state("12.5", "gal"), None),
        (_state("12.5", None), None),
        (_state("unavailable"), None),
        (_state("unknown"), None),
        (_state("abc"), None),
        (_state("nan"), None),
        (_state("inf"), None),
        (None, None),
    ],
)
def test_the_value_in_kwh(state: State | None, expected: float | None) -> None:
    assert kwh_of(state) == expected


def test_a_rise_is_the_energy_between_two_readings() -> None:
    tracker = RiseTracker()
    assert tracker.update(100.0, T0) is None  # the first reading is only a starting point

    rise = tracker.update(100.5, T0 + timedelta(minutes=1))

    assert rise is not None
    assert (rise.kwh, rise.start, rise.end) == (0.5, T0, T0 + timedelta(minutes=1))


def test_a_quiet_minute_books_nothing_and_the_next_step_lands_in_its_own_minute() -> None:
    tracker = RiseTracker()
    tracker.update(100.0, T0)
    assert tracker.update(100.0, T0 + timedelta(minutes=1)) is None

    rise = tracker.update(100.2, T0 + timedelta(minutes=2))

    assert rise is not None
    assert rise.start == T0 + timedelta(minutes=1)


def test_a_meter_reset_is_not_booked_and_counting_restarts() -> None:
    tracker = RiseTracker()
    tracker.update(5000.0, T0)
    assert tracker.update(3.0, T0 + timedelta(minutes=1)) is None

    rise = tracker.update(3.4, T0 + timedelta(minutes=2))

    assert rise is not None
    assert round(rise.kwh, 6) == 0.4


def test_a_hole_in_the_readings_is_not_bridged() -> None:
    tracker = RiseTracker()
    tracker.update(100.0, T0)
    assert tracker.update(None, T0 + timedelta(minutes=1)) is None

    assert tracker.update(104.0, T0 + timedelta(minutes=2)) is None


def test_a_jump_no_supply_could_deliver_is_refused() -> None:
    tracker = RiseTracker()
    tracker.update(100.0, T0)

    assert tracker.update(160.0, T0 + timedelta(minutes=1)) is None


def test_a_negative_reading_is_left_out_and_never_becomes_the_baseline() -> None:
    tracker = RiseTracker()
    tracker.update(100.0, T0)
    assert tracker.update(-5.0, T0 + timedelta(minutes=1)) is None

    # Counting from the negative value would book 105 kWh here.
    assert tracker.update(100.2, T0 + timedelta(minutes=2)) is None
    assert [item.reason for item in tracker.excluded] == ["negative", "gap"]
    assert tracker.latest_suspect is not None
    assert tracker.latest_suspect.reason == "negative"


def test_a_jump_is_reported_with_its_size_and_time() -> None:
    tracker = RiseTracker()
    tracker.update(100.0, T0)
    tracker.update(160.0, T0 + timedelta(minutes=1))

    [item] = tracker.excluded
    assert (item.reason, item.kwh, item.at) == ("too_large", 60.0, T0 + timedelta(minutes=1))


def test_the_limit_is_the_one_given() -> None:
    tracker = RiseTracker(max_kw=6.0)
    tracker.update(100.0, T0)

    assert tracker.update(100.2, T0 + timedelta(minutes=1)) is None  # 12 kW for a minute
    assert tracker.excluded[-1].reason == "too_large"
    assert tracker.update(100.3, T0 + timedelta(minutes=11)) is not None  # 0.6 kW over ten


def test_a_reset_is_ordinary_and_not_suspect() -> None:
    tracker = RiseTracker()
    tracker.update(5000.0, T0)
    tracker.update(3.0, T0 + timedelta(minutes=1))

    assert [item.reason for item in tracker.excluded] == ["reset"]
    assert tracker.latest_suspect is None


def test_the_first_reading_is_not_a_gap() -> None:
    tracker = RiseTracker()
    tracker.update(None, T0)
    tracker.update(100.0, T0 + timedelta(minutes=1))

    assert not tracker.excluded


def test_a_meter_that_comes_back_after_a_hole_reports_the_gap() -> None:
    tracker = RiseTracker()
    tracker.update(100.0, T0)
    tracker.update(None, T0 + timedelta(minutes=1))
    tracker.update(104.0, T0 + timedelta(minutes=2))

    [item] = tracker.excluded
    assert (item.reason, item.kwh) == ("gap", None)
    assert tracker.latest_suspect is None  # a gap is not a bad reading


def test_the_kept_exclusions_are_bounded() -> None:
    tracker = RiseTracker()
    for minute in range(60):
        tracker.update(1000.0 if minute % 2 == 0 else 0.0, T0 + timedelta(minutes=minute))

    assert len(tracker.excluded) == 20
