"""Starting shapes for a tariff typed in by the household.

A template only fills the form: the name of the main rate and the name and hours of one timed
rate. The household types the prices. The result is the same saved rates as a tariff typed from
nothing, and goes through the same compile step and checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TimedShape:
    """A timed rate: its name and the hours it applies each day."""

    name: str
    start: str
    end: str


@dataclass(frozen=True)
class Template:
    """The name of the main rate, and the timed rate the shape adds, if any."""

    base_name: str
    timed: TimedShape | None = None


BLANK = "blank"
DEFAULT_BASE_NAME = "Day"

TEMPLATES: dict[str, Template] = {
    "flat": Template("All day"),
    "day_night": Template("Day", TimedShape("Night", "23:00:00", "08:00:00")),
    "peak_offpeak": Template("Off-peak", TimedShape("Peak", "17:00:00", "19:00:00")),
    "cheap_midday": Template("Day", TimedShape("Midday", "11:00:00", "15:00:00")),
    "cheap_overnight": Template("Day", TimedShape("Overnight", "02:00:00", "06:00:00")),
    BLANK: Template(DEFAULT_BASE_NAME),
}


def timed_periods(template: Template, rate: float | None) -> list[dict[str, Any]]:
    """The saved timed rates for *template* at the price typed, none for a shape without one."""
    if template.timed is None or rate is None:
        return []
    shape = template.timed
    return [{"name": shape.name, "rate": rate, "start": shape.start, "end": shape.end}]
