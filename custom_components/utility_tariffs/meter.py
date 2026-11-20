"""Reads the user's energy meters and turns each reading into the energy used since the last.

A meter is a sensor whose value only ever rises. A reading that is missing, not a number, negative,
in an unknown unit or lower than the last one gives no energy for that step: the next reading
becomes the new starting point, so a restart or a meter reset never books a false total. A rise
larger than the supply could deliver in the time is left out too. Each exclusion is kept with its
reason, so it can be reported.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import State

KWH_PER_UNIT = {"kWh": 1.0, "Wh": 0.001, "MWh": 1000.0}
# A rise that no home supply could deliver in the time that passed is a jump in the meter, not use.
MAX_POWER_KW = 100.0
UNUSABLE_STATES = ("unknown", "unavailable", "")
MAX_KEPT_EXCLUSIONS = 20

# Why a step was left out of the bill. A reset and a gap are ordinary. The other two mean the meter
# gave a value it could not have counted, so they raise a repair issue.
RESET = "reset"
GAP = "gap"
TOO_LARGE = "too_large"
NEGATIVE = "negative"
SUSPECT = (TOO_LARGE, NEGATIVE)


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


@dataclass(frozen=True)
class Exclusion:
    """One step the bill left out: why, when, and the rise it would have booked, if known."""

    reason: str
    at: datetime
    kwh: float | None


class RiseTracker:
    """Remembers one meter's last reading and gives the rise since it.

    A reading that cannot be booked is kept in `excluded`, with the reason, so diagnostics and a
    repair issue can say what was left out and when.
    """

    def __init__(self, max_kw: float = MAX_POWER_KW) -> None:
        self._last: float | None = None
        self._at: datetime | None = None
        self._max_kw = max_kw if max_kw > 0 else MAX_POWER_KW
        self._had_reading = False
        self.latest_suspect: Exclusion | None = None
        self.excluded: deque[Exclusion] = deque(maxlen=MAX_KEPT_EXCLUSIONS)

    def update(self, value_kwh: float | None, now: datetime) -> Rise | None:
        """The rise since the previous reading, or None when there is none to book."""
        previous, at = self._last, self._at
        if value_kwh is not None and value_kwh < 0:
            self._leave_out(NEGATIVE, now, value_kwh)
            value_kwh = None
        self._last, self._at = value_kwh, now
        if value_kwh is None:
            return None
        if previous is None or at is None:
            if self._had_reading:
                self._leave_out(GAP, now, None)  # the meter is back, the use in between is unknown
            self._had_reading = True
            return None
        return self._rise(previous, at, value_kwh, now)

    def _rise(self, previous: float, at: datetime, value_kwh: float, now: datetime) -> Rise | None:
        kwh = value_kwh - previous
        hours = (now - at).total_seconds() / 3600
        if kwh < 0:
            self._leave_out(RESET, now, kwh)  # a new baseline, no use for this step
        elif kwh > self._max_kw * hours:
            self._leave_out(TOO_LARGE, now, kwh)
        elif kwh > 0:
            return Rise(kwh, at, now)
        return None

    def _leave_out(self, reason: str, at: datetime, kwh: float | None) -> None:
        exclusion = Exclusion(reason, at, kwh)
        self.excluded.append(exclusion)
        if reason in SUSPECT:
            self.latest_suspect = exclusion
