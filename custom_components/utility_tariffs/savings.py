"""The saving from solar and a battery in the current bill period, from the recorded history."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from .const import CONF_BATTERY_CAPACITY, CONF_BATTERY_WEAR
from .coordinator import TariffData
from .lib.tariff import (
    Battery,
    DefinitionSavings,
    PeriodRules,
    SavingsOptions,
    SlotDay,
    SlotHistory,
    bill_period_bounds,
    definition_savings,
    months_of,
    start_day_of,
    start_month_of,
)

LOOKBACK_DAYS = 7  # how far back to look for the charge the battery had when the period began


def opening_charge(history: SlotHistory, first_day: date, through: date) -> float | None:
    """The battery charge when the period began.

    The last reading before the period, else the first reading inside it, which counts the
    change in stored energy from when it was first seen.
    """
    start = first_day - timedelta(days=LOOKBACK_DAYS)
    earlier = [_readings(day) for day in history.between(start, first_day - timedelta(days=1))]
    if any(earlier):
        return next(r[-1] for r in reversed(earlier) if r)
    inside = [_readings(day) for day in history.between(first_day, through)]
    return next((r[0] for r in inside if r), None)


def _readings(day: SlotDay) -> list[float]:
    return [v for v in day.soc_pct if v is not None]


def battery_of(options: Mapping[str, Any], opening: float | None) -> Battery | None:
    capacity = options.get(CONF_BATTERY_CAPACITY)
    if not capacity:
        return None
    return Battery(float(capacity), opening, float(options.get(CONF_BATTERY_WEAR, 0.0)))


def saving_so_far(
    history: SlotHistory, data: TariffData, options: Mapping[str, Any], now: datetime
) -> DefinitionSavings | None:
    """The saving this bill period so far, or None while no house load has been recorded."""
    definition = data.definition
    today = now.astimezone(definition.timezone).date()
    first, _next = bill_period_bounds(
        start_day_of(definition), today, months_of(definition), start_month_of(definition)
    )
    battery = battery_of(options, opening_charge(history, first, today))
    rules = PeriodRules(is_holiday=data.is_holiday)
    try:
        return definition_savings(history, definition, today, SavingsOptions(battery, rules))
    except ValueError:
        return None
