"""Find every plan of the store that fits the current tariff, and sum up how they rank.

`lib/tariffranking` prices plans over measured usage. This module lists which plans to price and
turns the result into what a sensor shows. It re-prices past usage and never changes the tariff.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from .lib.tariff import DefinitionError, TariffDefinition
from .lib.tariffranking import (
    TOP,
    Candidate,
    Ranked,
    SearchResult,
    Unit,
    Window,
    rank_sentence,
)
from .lib.tariffstore import StoreError

_LOG = logging.getLogger(__name__)
ALL_AREAS = "all"
READ_ERRORS = (StoreError, DefinitionError, OSError, ValueError, KeyError, TypeError)
CURRENT = "current"
LISTED = 5  # plans named in the ranking, as well as the current one
WINDOW = Window(Unit.BILLS, 1)  # the last whole bill
MIN_SAVING_SHARE = 0.05  # a cheaper plan is suggested when it would have saved this share


class StoreReader(Protocol):
    async def async_providers(self, country: str) -> dict[str, str]: ...

    async def async_tariffs(self, country: str, provider: str, on: date) -> dict[str, str]: ...

    async def async_areas(
        self, country: str, provider: str, tariff: str, on: date
    ) -> dict[str, str]: ...

    async def async_definition(  # noqa: PLR0913
        self,
        country: str,
        provider: str,
        tariff: str,
        on: date,
        area: str = "all",
        export: str | None = None,
    ) -> TariffDefinition: ...


@dataclass
class Gathered:
    """The plans found and how many were left out."""

    candidates: list[Candidate] = field(default_factory=list)
    other_area: int = 0
    unreadable: int = 0


def plan_key(provider: str, tariff: str, area: str) -> str:
    return f"{provider}/{tariff}/{area}"


@dataclass(frozen=True)
class Where:
    """Which plans fit: the country and day to read, the area wanted and the plan to leave out."""

    country: str
    on: date
    area: str | None
    current_key: str | None


async def gather(store: StoreReader, where: Where) -> Gathered:
    """Every plan in force on *on* in *country* that fits *area*, bar the current plan.

    A plan with no areas fits. A plan that holds only other areas, or cannot be read, is counted
    and left out, never guessed.
    """
    found = Gathered()
    for provider in await store.async_providers(where.country):
        for tariff in await store.async_tariffs(where.country, provider, where.on):
            await _add(store, found, (provider, tariff), where)
    return found


async def _add(store: StoreReader, found: Gathered, plan: tuple[str, str], where: Where) -> None:
    provider, tariff = plan
    try:
        areas = await store.async_areas(where.country, provider, tariff, where.on)
        wanted = where.area
        chosen = wanted if wanted and wanted in areas else ALL_AREAS if ALL_AREAS in areas else None
        if chosen is None:
            found.other_area += 1
            return
        key = plan_key(provider, tariff, chosen)
        if key == where.current_key:
            return
        definition = await store.async_definition(
            where.country, provider, tariff, where.on, area=chosen
        )
    except READ_ERRORS as err:
        _LOG.debug("Left out %s/%s: %s", provider, tariff, err)
        found.unreadable += 1
        return
    label = f"{definition.provider.name} {definition.name}"
    found.candidates.append(Candidate(key, label, definition))


@dataclass(frozen=True)
class RankedPlan:
    rank: int
    name: str
    bill: float
    yours: bool


@dataclass(frozen=True)
class PlanRanking:
    """What the ranking shows."""

    current_rank: int
    compared: int
    plans: tuple[RankedPlan, ...]  # the cheapest few, and the current plan wherever it stands
    cheapest: str  # the name of the cheapest plan, "" when the current plan is it
    saving: float  # the current bill less the cheapest plan's, never negative
    current_bill: float
    sentence: str
    first_day: date
    last_day: date
    days_recorded: int
    left_out: int  # plans that could not be priced

    @property
    def worth_suggesting(self) -> bool:
        """True when a cheaper plan would have saved a real share of the bill."""
        return self.saving > 0 and self.saving >= self.current_bill * MIN_SAVING_SHARE


def _sentence(result: SearchResult, cheapest: Ranked, saving: float) -> str:
    standing = rank_sentence(result)
    if cheapest.key == CURRENT:
        return standing
    return (
        f"{standing} The last bill would have been cheapest on {cheapest.label}, {saving:.2f} less."
    )


def summarise(result: SearchResult, left_out: int) -> PlanRanking:
    """The best `LISTED` plans and the current one, with the current plan's standing."""
    chosen = [r for r in result.ranked if r.rank <= LISTED or r.key == CURRENT]
    cheapest = result.ranked[0]
    yours = result.ranked[result.current_rank - 1]
    saving = round(max(yours.total - cheapest.total, 0.0), 2)
    return PlanRanking(
        current_rank=result.current_rank,
        compared=result.compared,
        plans=tuple(
            RankedPlan(
                r.rank, "Your plan" if r.key == CURRENT else r.label, r.total, r.key == CURRENT
            )
            for r in chosen
        ),
        cheapest="" if cheapest.key == CURRENT else cheapest.label,
        saving=saving,
        current_bill=yours.total,
        sentence=_sentence(result, cheapest, saving),
        first_day=result.first_day,
        last_day=result.last_day,
        days_recorded=result.days_recorded,
        left_out=left_out + result.skipped,
    )


def attributes(ranking: PlanRanking) -> dict[str, Any]:
    """The state attributes of the rank sensor."""
    return {
        "summary": ranking.sentence,
        "plans_compared": ranking.compared,
        "period_start": ranking.first_day.isoformat(),
        "period_end": ranking.last_day.isoformat(),
        "days_recorded": ranking.days_recorded,
        "plans_left_out": ranking.left_out,
        "top_plans": [
            {"rank": p.rank, "plan": p.name, "bill": round(p.bill, 2), "yours": p.yours}
            for p in ranking.plans
        ],
        "top": TOP,
    }
