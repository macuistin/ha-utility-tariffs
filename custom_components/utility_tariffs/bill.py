"""The bill so far for the current bill period, priced from the energy the meters counted."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from utility_tariffs_lib.tariff import MissingLoad, PeriodBill, SlotHistory, price_period

from .bill_period import period_rules
from .coordinator import TariffData


def bill_so_far(
    history: SlotHistory, data: TariffData, options: Mapping[str, Any], now: datetime
) -> PeriodBill | None:
    """The period holding today, priced under the tariff in force, up to and including today.

    The bill dates in *options* replace the tariff's own when the user has set them. A tariff
    with a connected load charge has no bill until the load is set, so this returns None.
    """
    today = now.astimezone(data.definition.timezone).date()
    rules = period_rules(options, data.is_holiday)
    try:
        return price_period(history, data.definition, today, rules)
    except MissingLoad:
        return None
