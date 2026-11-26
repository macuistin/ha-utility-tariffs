"""The bill line by line, with and without the system, and day by day."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from utility_tariffs_lib.tariff import (
    DefinitionSavings,
    PeriodBill,
    SavingsOptions,
    SlotHistory,
    definition_savings,
)

from .bill_period import period_rules
from .bill_summary import statement
from .coordinator import TariffData

DAILY_DAYS = 62  # the most recent days listed, so a long bill period keeps the attribute small


def _amounts(bill: PeriodBill) -> dict[str, Decimal]:
    """The lines of a bill by name. Lines with one name are added together."""
    amounts: dict[str, Decimal] = {}
    for label, amount, _included in statement("bill", bill.priced.root):
        amounts[label] = amounts.get(label, Decimal(0)) + amount
    return amounts


def _included(bill: PeriodBill) -> set[str]:
    """The names of the lines that are already part of the others, such as VAT in the price."""
    return {label for label, _amount, included in statement("bill", bill.priced.root) if included}


def paid_lines(bill: PeriodBill) -> list[dict[str, Any]]:
    """Each line of the bill so far, in the order the bill works them out."""
    included = _included(bill)
    return [
        {"line": label, "paid": float(amount), "included": label in included}
        for label, amount in _amounts(bill).items()
    ]


def compared_lines(saving: DefinitionSavings) -> list[dict[str, Any]]:
    """Each line paid and the same line had the whole house load come from the grid.

    A line marked `included` is part of the other lines, so leave it out of a sum. A line one
    bill has and the other lacks counts as zero in the other, so a band the system emptied
    still shows what it would have cost.
    """
    paid, without = _amounts(saving.actual), _amounts(saving.without_system)
    zero = Decimal(0)
    included = _included(saving.actual) | _included(saving.without_system)
    return [
        {
            "line": label,
            "paid": float(paid.get(label, zero)),
            "would_have_paid": float(without.get(label, zero)),
            "saved": float(without.get(label, zero) - paid.get(label, zero)),
            "included": label in included,
        }
        for label in [*paid, *(k for k in without if k not in paid)]
    ]


def _day_saving(
    history: SlotHistory, data: TariffData, options: Mapping[str, Any], day: date
) -> DefinitionSavings | None:
    """One day priced on its own: a period charge is shared by the days priced."""
    rules = replace(period_rules(options, data.is_holiday), since=day)
    try:
        return definition_savings(history, data.definition, day, SavingsOptions(None, rules))
    except ValueError:
        return None  # no house load was recorded that day


def daily_series(
    history: SlotHistory, data: TariffData, options: Mapping[str, Any], saving: DefinitionSavings
) -> list[dict[str, Any]]:
    """What each day of the bill period so far cost, and would have cost without the system.

    The battery's stored energy and wear are not split by day, so `saved` is the bill difference.
    Days without a recorded house load are left out, not shown as zero.
    """
    first = saving.actual.priced_from or saving.actual.first_day
    last = saving.actual.through
    start = max(first, last - timedelta(days=DAILY_DAYS - 1))
    series: list[dict[str, Any]] = []
    for offset in range((last - start).days + 1):
        day = start + timedelta(days=offset)
        priced = _day_saving(history, data, options, day)
        if priced is not None:
            series.append(
                {
                    "date": day.isoformat(),
                    "paid": float(priced.actual.priced.total),
                    "would_have_paid": float(priced.without_system.priced.total),
                    "saved": float(priced.bill_difference),
                }
            )
    return series
