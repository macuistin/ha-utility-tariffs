"""The bill period the user chose, laid over the tariff's own dates."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from .const import CONF_BILL_MONTHS, CONF_BILL_START_DAY, CONF_BILL_START_MONTH
from .lib.tariff import PeriodRules, TariffDefinition, months_of, start_day_of, start_month_of


def period_rules(options: Mapping[str, Any], is_holiday: Callable[[date], bool]) -> PeriodRules:
    """The saved bill dates as rules. A date the user left unset follows the tariff."""

    def chosen(key: str) -> int | None:
        value = options.get(key)
        return int(value) if value else None

    return PeriodRules(
        start_day=chosen(CONF_BILL_START_DAY),
        months=chosen(CONF_BILL_MONTHS),
        start_month=chosen(CONF_BILL_START_MONTH),
        is_holiday=is_holiday,
    )


def period_dates(definition: TariffDefinition, rules: PeriodRules) -> tuple[int, int, int]:
    """Start day, months and start month in force: the user's, else the tariff's."""
    return (
        rules.start_day or start_day_of(definition),
        rules.months or months_of(definition),
        rules.start_month or start_month_of(definition),
    )
