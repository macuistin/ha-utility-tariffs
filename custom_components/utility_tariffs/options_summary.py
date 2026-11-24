"""One line for each Configure page saying what is set now, shown under its name in the menu."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import (
    CHEAP_BAND,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_DISCHARGE_ENERGY,
    CONF_BATTERY_SOC,
    CONF_BILL_MONTHS,
    CONF_BILL_START_DAY,
    CONF_CHEAP_RULE,
    CONF_COUNTRY,
    CONF_EXPORT_ENERGY,
    CONF_HOUSE_ENERGY,
    CONF_IMPORT_ENERGY,
    CONF_MANUAL,
    CONF_WINDOW_MINUTES,
    DEFAULT_WINDOW_MINUTES,
    SERVICE_GAS,
)

NOT_SET = "not set"


def tariff_line(title: str, data: Mapping[str, Any], staged: str | None) -> str:
    """The followed plan, or the plan chosen and waiting to be saved."""
    if staged is not None:
        return f"changes to {staged} when you save"
    if CONF_MANUAL in data:
        return f"{title}, your own rates"
    country = data.get(CONF_COUNTRY)
    return f"{title} ({country})" if country else title


def meters_line(options: Mapping[str, Any], service: str) -> str:
    keys = (
        (("import", CONF_IMPORT_ENERGY),)
        if service == SERVICE_GAS
        else (
            ("import", CONF_IMPORT_ENERGY),
            ("export", CONF_EXPORT_ENERGY),
            ("whole home", CONF_HOUSE_ENERGY),
        )
    )
    chosen = [f"{label} {options[key]}" for label, key in keys if options.get(key)]
    return ", ".join(chosen) if chosen else "none chosen, prices only"


def battery_line(options: Mapping[str, Any]) -> str:
    parts = []
    if options.get(CONF_BATTERY_CAPACITY) is not None:
        parts.append(f"battery {options[CONF_BATTERY_CAPACITY]:g} kWh")
    if options.get(CONF_BATTERY_SOC):
        parts.append(f"charge {options[CONF_BATTERY_SOC]}")
    if options.get(CONF_BATTERY_DISCHARGE_ENERGY):
        parts.append(f"discharge {options[CONF_BATTERY_DISCHARGE_ENERGY]}")
    return ", ".join(parts) if parts else "no battery set"


def bills_line(options: Mapping[str, Any]) -> str:
    day, months = options.get(CONF_BILL_START_DAY), options.get(CONF_BILL_MONTHS)
    if not day and not months:
        return "follows the tariff's own bill dates"
    parts = [f"bill starts on day {day}"] if day else []
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''} a bill")
    return ", ".join(parts)


def windows_line(options: Mapping[str, Any]) -> str:
    minutes = options.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES)
    rule = "only the cheapest band" if options.get(CONF_CHEAP_RULE, CHEAP_BAND) == CHEAP_BAND else (
        "any band at or below the average"
    )
    return f"{minutes} minute windows, cheap is {rule}"
