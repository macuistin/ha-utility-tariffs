"""The bill so far for the current bill period, priced from the energy the meters counted."""

from __future__ import annotations

from datetime import datetime

from .coordinator import TariffData
from .lib.tariff import PeriodBill, PeriodRules, SlotHistory, price_period


def bill_so_far(history: SlotHistory, data: TariffData, now: datetime) -> PeriodBill:
    """The period holding today, priced under the tariff in force, up to and including today."""
    today = now.astimezone(data.definition.timezone).date()
    return price_period(history, data.definition, today, PeriodRules(is_holiday=data.is_holiday))
