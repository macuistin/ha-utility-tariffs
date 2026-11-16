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
