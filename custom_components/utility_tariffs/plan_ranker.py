"""Keeps the ranking of every store plan against the followed tariff up to date.

Once at start-up and once a day, shortly after the day's usage is final, every plan of the
tariff's country and area is priced over the last whole bill and the ranking is kept for the
sensors. It re-prices measured usage and writes nothing, and it never changes the tariff. A store
that cannot be read, or too little history, leaves the last ranking in place.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util
from utility_tariffs_lib.tariffranking import Candidate, Usage, ranges, search

from .bill_period import period_dates, period_rules
from .const import CONF_AREA, CONF_MANUAL, CONF_PROVIDER, CONF_TARIFF, DOMAIN
from .plan_search import (
    CURRENT,
    READ_ERRORS,
    WINDOW,
    PlanRanking,
    Where,
    gather,
    plan_key,
    summarise,
)

if TYPE_CHECKING:
    from .coordinator import TariffCoordinator

_LOG = logging.getLogger(__name__)
RANK_HOUR = 0
RANK_MINUTE = 30  # after the day's slots are final
ISSUE_ID = "cheaper_plan"


class PlanRanker:
    """Holds the latest ranking. The slot history is read fresh each time it refreshes."""

    def __init__(self, coordinator: TariffCoordinator) -> None:
        self._coordinator = coordinator
        self.ranking: PlanRanking | None = None

    async def async_refresh(self, today: date) -> PlanRanking | None:
        """Price every plan again. Returns the new ranking, or None when none could be made."""
        coordinator = self._coordinator
        accountant = coordinator.accountant
        if accountant is None:
            return None
        data = coordinator.data
        definition = data.definition
        entry = coordinator.config_entry
        area = entry.data.get(CONF_AREA)
        through = today - timedelta(days=1)
        try:
            await coordinator.access.async_refresh()
            where = Where(definition.country, through, area, _current_key(entry.data))
            found = await gather(coordinator.access, where)
        except READ_ERRORS as err:
            _LOG.debug("The plan ranking could not read the store: %s", err)
            return None
        rules = period_rules(entry.options, data.is_holiday)
        start_day, months, _month = period_dates(definition, rules)
        spans = ranges(WINDOW, through, start_day, months)
        export = definition.export_prices.base.price
        current = Candidate(CURRENT, "Your plan", definition)
        others = [
            Candidate(c.key, c.label, c.definition, Decimal(export)) for c in found.candidates
        ]
        usage = Usage(accountant.store.history, spans, data.is_holiday, rules.load_kw)
        result = await coordinator.hass.async_add_executor_job(search, usage, current, others)
        if result.days_recorded == 0:
            return self.ranking
        self.ranking = summarise(result, found.other_area + found.unreadable)
        self._report(self.ranking)
        return self.ranking

    def _report(self, ranking: PlanRanking) -> None:
        """Raise a repair issue when a cheaper plan would have saved a real share, else clear it."""
        hass = self._coordinator.hass
        if not ranking.worth_suggesting:
            ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
            return
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_ID,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_ID,
            translation_placeholders={"plan": ranking.cheapest, "saving": f"{ranking.saving:.2f}"},
        )

    @callback
    def async_start(self) -> None:
        """Rank once now and every day at 00:30 local time, until the entry unloads."""
        entry = self._coordinator.config_entry
        hass = self._coordinator.hass

        async def run() -> None:
            try:
                await self.async_refresh(dt_util.now().date())
            except (ValueError, OSError, KeyError, TypeError) as err:
                _LOG.warning("The plan ranking could not be worked out: %s", err)
            self._coordinator.async_update_listeners()

        @callback
        def daily(_now: object) -> None:
            entry.async_create_background_task(hass, run(), "utility_tariffs plan ranking")

        entry.async_create_background_task(hass, run(), "utility_tariffs plan ranking")
        entry.async_on_unload(
            async_track_time_change(hass, daily, hour=RANK_HOUR, minute=RANK_MINUTE, second=0)
        )
        entry.async_on_unload(lambda: ir.async_delete_issue(hass, DOMAIN, ISSUE_ID))


def _current_key(data: Mapping[str, Any]) -> str | None:
    """The store key of the followed plan, or None for rates the household typed in."""
    if CONF_MANUAL in data:
        return None
    return plan_key(data[CONF_PROVIDER], data[CONF_TARIFF], data[CONF_AREA])
