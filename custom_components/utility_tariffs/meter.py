"""Reads the user's energy meters and turns each reading into the energy used since the last.

A meter is a sensor whose value only ever rises. A reading that is missing, not a number, in an
unknown unit or lower than the last one gives no energy for that step: the next reading becomes the
new starting point, so a restart or a meter reset never books a false total.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import State

KWH_PER_UNIT = {"kWh": 1.0, "Wh": 0.001, "MWh": 1000.0}
# A rise that no home supply could deliver in the time that passed is a jump in the meter, not use.
MAX_POWER_KW = 100.0
UNUSABLE_STATES = ("unknown", "unavailable", "")


@dataclass(frozen=True)
class Rise:
    """Energy that a meter counted between two readings."""

    kwh: float
    start: datetime
    end: datetime


def kwh_of(state: State | None) -> float | None:
    """The meter's value in kWh, or None when it cannot be read as an energy."""
    if state is None or state.state in UNUSABLE_STATES:
        return None
    factor = KWH_PER_UNIT.get(str(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)))
    if factor is None:
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    return value * factor if value == value and abs(value) != float("inf") else None


class RiseTracker:
    """Remembers one meter's last reading and gives the rise since it."""

    def __init__(self) -> None:
        self._last: float | None = None
        self._at: datetime | None = None

    def update(self, value_kwh: float | None, now: datetime) -> Rise | None:
        """The rise since the previous reading, or None when there is none to book."""
        previous, at = self._last, self._at
        self._last, self._at = value_kwh, now
        if value_kwh is None or previous is None or at is None:
            return None
        kwh = value_kwh - previous
        hours = (now - at).total_seconds() / 3600
        if kwh <= 0 or hours <= 0 or kwh > MAX_POWER_KW * hours:
            return None
        return Rise(kwh, at, now)
