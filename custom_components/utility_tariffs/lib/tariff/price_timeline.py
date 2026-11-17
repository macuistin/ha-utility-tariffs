"""price_timeline.py: the prices over a range that crosses a revision or follows a price feed.

`price_curve` prices one definition. Two things need more. A revision that starts later in the
range has its own definition, so the range is cut where each revision starts and each part is
priced with the definition in force there. And a tariff on a price series (`series_energy`) has no
band price: its slots come from the published prices, so they stop where the series stops. Nothing
is extrapolated and nothing is priced as zero. The caller reads `known_until` to see how far the
prices are known.

The price of a series slot is the series price taken through the bill, so a tax or a discount
after the energy line is in the price, as it is for a band price.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from .bands import band_at, export_band_at, no_holidays
from .definition import TariffDefinition
from .engine import BillInputs, price_bill
from .price_curve import _STEP, MarginalPrices, PriceSlot, marginal_prices, price_curve
from .price_series import PriceSeries, series_names


@dataclass(frozen=True)
class Revision:
    """A definition and the first local day it applies."""

    first_day: date
    definition: TariffDefinition


def _start_of(revision: Revision) -> datetime:
    return datetime.combine(revision.first_day, datetime.min.time(), revision.definition.timezone)


def series_factor(definition: TariffDefinition, name: str) -> Decimal:
    """What one unit of a series price becomes in the bill: 1 when nothing follows the energy
    line, and for example 1.05 when VAT is added after it."""
    names = {other: Decimal(0) for other in series_names(definition)}
    base = price_bill(definition, BillInputs(30, 30, {}, Decimal(0), import_cost_by_series=names))
    names[name] = _STEP
    more = price_bill(definition, BillInputs(30, 30, {}, Decimal(0), import_cost_by_series=names))
    return (more.total - base.total) / _STEP


def series_curve(  # noqa: PLR0913
    definition: TariffDefinition,
    series: PriceSeries,
    start: datetime,
    end: datetime,
    is_holiday: Callable[[date], bool] = no_holidays,
) -> tuple[PriceSlot, ...]:
    """The slots of a one-series tariff from *start* to *end*, as far as *series* covers them.
    Export prices come from the document, as for any tariff."""
    (name,) = series_names(definition)
    factor = series_factor(definition, name)
    marginal = marginal_prices(definition)
    slots: list[PriceSlot] = []
    cursor = max(start, series.start)
    while cursor < min(end, series.end):
        offset = (cursor - series.start) // series.interval
        edge = min(end, series.end, series.start + series.interval * (offset + 1))
        slot = _published(definition, marginal, cursor, edge, series.price_at(cursor) * factor,
                          is_holiday)
        if slots and slots[-1].end == slot.start and slots[-1].import_price == slot.import_price \
                and slots[-1].export_band == slot.export_band:
            slot = PriceSlot(slots.pop().start, slot.end, slot.import_band, slot.export_band,
                             slot.import_price, slot.export_price, slot.source)
        slots.append(slot)
        cursor = edge
    return tuple(slots)


def _published(  # noqa: PLR0913
    definition: TariffDefinition, marginal: MarginalPrices, start: datetime, end: datetime,
    price: Decimal, is_holiday: Callable[[date], bool],
) -> PriceSlot:
    in_band = band_at(definition, start, is_holiday)
    out_band = export_band_at(definition, start, is_holiday)
    return PriceSlot(start, end, in_band, out_band, price, marginal.export_prices[out_band],
                     "published")


def price_timeline(  # noqa: PLR0913
    revisions: Sequence[Revision],
    start: datetime,
    end: datetime,
    series: Mapping[str, Sequence[PriceSeries]] | None = None,
    is_holiday: Callable[[date], bool] = no_holidays,
) -> tuple[PriceSlot, ...]:
    """The prices from *start* to *end* (aware times) over one or more revisions.

    *revisions* are in date order. The first applies from *start*, whatever its first day, and each
    later one from its first day at local midnight. *series* holds, for the name of each series a
    definition uses, the runs of published prices (`series_runs`). A series tariff with no run
    that covers part of the range gives no slots for that part."""
    if not revisions:
        raise ValueError("a timeline needs at least one revision")
    if end <= start:
        raise ValueError("end must be after start")
    slots: list[PriceSlot] = []
    for position, revision in enumerate(revisions):
        part_start = start if position == 0 else max(start, _start_of(revision))
        part_end = end if position + 1 == len(revisions) else min(end, _start_of(
            revisions[position + 1]))
        if part_start >= part_end:
            continue
        slots += _part(revision.definition, part_start, part_end, series or {}, is_holiday)
    return tuple(slots)


def _part(  # noqa: PLR0913
    definition: TariffDefinition, start: datetime, end: datetime,
    series: Mapping[str, Sequence[PriceSeries]], is_holiday: Callable[[date], bool],
) -> list[PriceSlot]:
    names = series_names(definition)
    if not names:
        return list(price_curve(definition, start, end, is_holiday))
    if len(names) > 1:
        raise ValueError("a tariff on more than one price series has no single price")
    found: list[PriceSlot] = []
    for run in series.get(names[0], ()):
        found += series_curve(definition, run, start, end, is_holiday)
    return sorted(found, key=lambda slot: slot.start)


def known_until(slots: Sequence[PriceSlot], start: datetime) -> datetime | None:
    """The end of the unbroken run of slots that begins at *start*, or None when none does."""
    reached: datetime | None = None
    for slot in slots:
        if reached is None and slot.start <= start < slot.end:
            reached = slot.end
        elif reached is not None and slot.start == reached:
            reached = slot.end
    return reached
