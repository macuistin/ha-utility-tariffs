"""The bill so far for the current bill period, priced from the energy the meters counted."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .bill_period import period_rules
from .coordinator import TariffData
from .lib.tariff import PeriodBill, SlotHistory, price_period


def bill_so_far(
    history: SlotHistory, data: TariffData, options: Mapping[str, Any], now: datetime
) -> PeriodBill:
    """The period holding today, priced under the tariff in force, up to and including today.

    The bill dates in *options* replace the tariff's own when the user has set them.
    """
    today = now.astimezone(data.definition.timezone).date()
    rules = period_rules(options, data.is_holiday)
    return price_period(history, data.definition, today, rules)
