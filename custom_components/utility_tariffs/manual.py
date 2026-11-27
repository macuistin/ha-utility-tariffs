"""A tariff typed in by the household, held in the config entry and priced like a store plan.

The rates are saved as plain values. They are written as a definition document through the same
compile step the store's plans pass, so the document is checked the same way and every sensor and
bill reads it as it would any other tariff. Nothing typed here is ever sent to the store.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, time
from typing import Any

from utility_tariffs_lib.tariff import (
    DefinitionError,
    Locale,
    RatePeriod,
    TariffConfig,
    TariffDefinition,
    definition_from_config,
)


@dataclass(frozen=True)
class CountryDefaults:
    """What the form starts from: the country, its currency and the VAT rate in force there."""

    country: str
    currency: str
    vat_percent: float = 0.0


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
HOLIDAY_RULES = ("normal", "weekend", "sunday")
OPEN_SINCE = date(2000, 1, 1)  # a typed tariff has no start date, so it has always applied


def _time(text: str) -> time:
    return time.fromisoformat(text).replace(second=0, microsecond=0)


def config_from(rates: dict[str, Any]) -> TariffConfig:
    """The saved rates as the tariff configuration the bill maths reads."""
    return TariffConfig(
        rate_periods=[
            RatePeriod(
                p["name"], float(p["rate"]), _time(p["start"]), _time(p["end"]),
                days=tuple(p.get("days", ())), holidays=p.get("holidays", "normal"),
            )
            for p in rates.get("periods", [])
        ],
        base_rate=float(rates["base_rate"]),
        base_rate_name=rates["base_rate_name"],
        export_rate=float(rates.get("export_rate", 0)),
        standing_charge=float(rates.get("standing_charge", 0)),
        pso_levy=float(rates.get("levy", 0)),
        vat_rate=float(rates.get("vat_rate", 0)),
        discount_rate=float(rates.get("discount_rate", 0)),
        bill_start_day=int(rates.get("bill_start_day", 1)),
        vat_included=bool(rates.get("vat_included", False)),
    )


def definition_from(rates: dict[str, Any], name: str) -> TariffDefinition:
    """The definition for saved rates. Raises DefinitionError when they cannot be written down."""
    locale = Locale(rates["currency"], rates["country"], rates["timezone"], OPEN_SINCE)
    return replace(definition_from_config(config_from(rates), locale), name=name)


def problem_with(rates: dict[str, Any], name: str) -> str | None:
    """Why the rates cannot be used, or None when they can."""
    try:
        definition_from(rates, name)
    except (DefinitionError, ValueError, KeyError) as err:
        return str(err)
    return None


def uses_holidays(rates: dict[str, Any]) -> bool:
    """Whether any timed rate treats a public holiday as a weekend day or a Sunday."""
    return any(p.get("holidays", "normal") != "normal" for p in rates.get("periods", []))
