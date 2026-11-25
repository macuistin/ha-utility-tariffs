"""Holds the followed tariff and its prices over time.

The definition is read from the store at start-up and every night shortly after midnight. A store
that cannot be read changes nothing: the prices already held keep working. Sensors work out the
current slot from the held prices, so the coordinator also wakes them at every half hour.

A tariff with fixed prices is priced for the next fortnight, with every revision the store already
holds for that time. A tariff on a price feed (Agile) is priced from the published half-hourly
prices: the last 28 days, for what a high and a low price look like, and as far ahead as they are
published. Tomorrow's prices appear in the afternoon, so from 16:00 to 20:00 the feed is read
again every half hour until they are held. Nothing is guessed for the part not yet published.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cached_property
from typing import TYPE_CHECKING, Literal

from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_change, async_track_utc_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from utility_tariffs_lib.tariff import (
    MarginalPrices,
    PriceSeries,
    PriceSlot,
    PriceStats,
    Revision,
    TariffDefinition,
    feed_of,
    known_until,
    marginal_prices,
    no_holidays,
    price_stats,
    price_timeline,
    series_names,
    series_runs,
)
from utility_tariffs_lib.tariffstore import StoreError

from .const import (
    CONF_AREA,
    CONF_COUNTRY,
    CONF_MANUAL,
    CONF_NAME,
    CONF_PROVIDER,
    CONF_TARIFF,
    DOMAIN,
)
from .country_reason import reason_for
from .freshness import STATUS_CURRENT, days_unreached, plan_ending, plan_status
from .fuel import Fuel
from .manual import definition_from
from .store import price_access, store_access

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .accountant import EnergyAccountant
    from .helper.store_access import PriceStoreAccess, TariffStoreAccess
    from .plan_ranker import PlanRanker

_LOGGER = logging.getLogger(__name__)
FIXED_HORIZON_DAYS = 14  # a fixed tariff is priced this far ahead, over every revision known
FEED_HORIZON_DAYS = 2  # a feed is read to the end of tomorrow, the furthest it is ever published
PAST_DAYS = 1  # yesterday, so the previous price is known just after midnight
FEED_PAST_DAYS = 28  # what a high and a low price look like is read from this many past days
REVISION_DAYS = 90  # a revision the store holds is listed this far ahead
PRICES_DUE_HOUR = 16  # tomorrow's Agile prices appear in the afternoon
PRICES_LATE_HOUR = 22  # and a repair is raised when they are still missing at night
ISSUE_PRICES_LATE = "prices_not_published"
ISSUE_PLAN_ENDING = "plan_ending"
ISSUE_STORE_UNREACHED = "store_unreached"
ISSUE_PLAN_ENDED = "plan_ended"
ISSUE_PLAN_WITHDRAWN = "plan_withdrawn"
STORE_ERRORS = (StoreError, OSError, ValueError, KeyError, TypeError)
type TariffConfigEntry = ConfigEntry[dict[str, TariffCoordinator]]


@dataclass(frozen=True)
class TariffData:
    """The tariff in force and its prices from local midnight for two days."""

    definition: TariffDefinition
    slots: tuple[PriceSlot, ...]
    holidays_known: bool  # False when the store holds no public holidays for the period
    is_holiday: Callable[[date], bool] = no_holidays
    revisions: tuple[Revision, ...] = ()  # the definition in force and any that start later
    feeds: tuple[str, ...] = ()  # the price feeds the tariff reads, empty for fixed prices
    horizon_end: datetime | None = None  # how far ahead the prices were asked for
    read_at: datetime | None = None  # when the store was last read, UTC. Unchanged on a failed read
    country_availability: str | None = None  # "available" or "partial", from the store's index
    country_reason: str | None = None  # what the store says is missing for a partial country

    @property
    def on_a_feed(self) -> bool:
        return bool(self.feeds)

    def known_until(self, moment: datetime) -> datetime | None:
        """The end of the run of prices known from *moment*, or None when none is held."""
        return known_until(self.slots, moment)

    def slot_at(self, moment: datetime) -> PriceSlot | None:
        for slot in self.slots:
            if slot.start <= moment < slot.end:
                return slot
        return None

    def next_change(self, moment: datetime) -> PriceSlot | None:
        """The first slot that starts after *moment* with a different import price."""
        current = self.slot_at(moment)
        for slot in self.slots:
            if slot.start > moment and (
                current is None or (slot.import_band, slot.import_price)
                != (current.import_band, current.import_price)
            ):
                return slot
        return None


    def previous_change(self, moment: datetime) -> PriceSlot | None:
        """The last slot before *moment* whose import price differs from the one in force."""
        current = self.slot_at(moment)
        for slot in reversed(self.slots):
            if slot.end <= moment and (
                current is None or (slot.import_band, slot.import_price)
                != (current.import_band, current.import_price)
            ):
                return slot
        return None

    @cached_property
    def marginal(self) -> MarginalPrices:
        """What one more kWh costs or earns in each band, worked out once per read."""
        return marginal_prices(self.definition)

    def day_stats(self, moment: datetime, flow: Literal["import", "export"]) -> PriceStats | None:
        """The prices over the local day holding *moment*, in the tariff's time zone."""
        local = moment.astimezone(self.definition.timezone)
        start = datetime.combine(local.date(), datetime.min.time(), self.definition.timezone)
        return price_stats(self.slots, start, start + timedelta(days=1), flow)


class TariffCoordinator(DataUpdateCoordinator[TariffData]):
    """Reads the tariff and keeps its price series."""

    config_entry: TariffConfigEntry

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry: TariffConfigEntry,
        subentry_id: str,
        access: TariffStoreAccess | None = None,
        prices: PriceStoreAccess | None = None,
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None
        )
        self.fuel = Fuel(entry, subentry_id)
        self._access = access if access is not None else store_access(hass, self.fuel.service)
        self._prices = prices if prices is not None else price_access(hass)
        # Set at start-up when the user has chosen an energy meter. None means no bill is kept.
        self.accountant: EnergyAccountant | None = None
        # Set with the accountant: the ranking of every store plan over the last whole bill.
        self.ranker: PlanRanker | None = None
        # "ended" or "withdrawn" while the store can no longer give this plan's prices.
        self._gone: str | None = None

    @property
    def service(self) -> str:
        return self.fuel.service

    @property
    def access(self) -> TariffStoreAccess:
        return self._access

    def plan_status(self, today: date) -> str:
        """The plan's status, from the data held and what the store last said about it."""
        if self.data is None:
            return self._gone or STATUS_CURRENT
        return plan_status(self.data, today, self._gone)

    async def async_refresh_store(self, *, clear: bool = False) -> None:
        """Read the store again now. With *clear*, the saved files are deleted first."""
        if clear:
            await self._access.async_clear_cache()
            await self._prices.async_clear_cache()
        else:
            await self._access.async_refresh()
        await self.async_refresh()

    async def _async_setup(self) -> None:
        """Read again every night, and wake the sensors at every half hour."""

        @callback
        def tick(_now: datetime) -> None:
            if self.data is not None:
                self.async_update_listeners()

        @callback
        def nightly(_now: datetime) -> None:
            self.fuel.async_create_background_task(
                self.hass, self.async_request_refresh(), "utility_tariffs nightly read"
            )

        self.fuel.async_on_unload(
            async_track_utc_time_change(self.hass, tick, minute=(0, 30), second=0)
        )
        self.fuel.async_on_unload(
            async_track_time_change(self.hass, nightly, hour=0, minute=5, second=0)
        )

        @callback
        def afternoon(now: datetime) -> None:
            if self.data is not None and self.data.on_a_feed and self._tomorrow_missing(now):
                self.fuel.async_create_background_task(
                    self.hass, self.async_request_refresh(), "utility_tariffs price read"
                )

        self.fuel.async_on_unload(
            async_track_time_change(
                self.hass, afternoon, hour=range(PRICES_DUE_HOUR, PRICES_LATE_HOUR),
                minute=(2, 32), second=0,
            )
        )

    def tomorrow_known(self, now: datetime) -> bool:
        """Whether the held prices reach the end of tomorrow, local time."""
        return self.data is not None and not self._tomorrow_missing(now)

    def _tomorrow_missing(self, now: datetime) -> bool:
        """Whether the held prices stop before the end of tomorrow, local time."""
        if self.data is None:
            return False
        zone = self.data.definition.timezone
        local = now.astimezone(zone)
        end = datetime.combine(
            local.date() + timedelta(days=FEED_HORIZON_DAYS), datetime.min.time(), zone
        )
        reached = self.data.known_until(now)
        return reached is None or reached < end

    async def _async_update_data(self) -> TariffData:
        today = dt_util.now().date()
        try:
            data = await self._read(today)
        except STORE_ERRORS as err:
            self._gone = await self._gone_state(today)
            self._set_gone_issues()
            if self._gone is not None and self.data is None:
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key=f"plan_{self._gone}",
                    translation_placeholders={"tariff": self.fuel.title},
                ) from err
            if self.data is not None:
                _LOGGER.warning("The tariff store could not be read, keeping saved prices: %s", err)
                self._check_freshness(self.data)
                return self.data
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="store_unreadable",
                translation_placeholders={"error": str(err)},
            ) from err
        self._gone = None
        self._set_gone_issues()
        self._check_freshness(data)
        return data

    async def _gone_state(self, today: date) -> str | None:
        """"ended" or "withdrawn" when the store says the plan is no longer offered, else None.
        A store that cannot be reached says nothing, so the plan is not called ended then."""
        entry = self.fuel.data
        if CONF_MANUAL in entry:
            return None
        try:
            state = await self._access.async_tariff_state(
                entry[CONF_COUNTRY], entry[CONF_PROVIDER], entry[CONF_TARIFF], today
            )
        except STORE_ERRORS:
            return None
        return None if state == STATUS_CURRENT else state

    def _set_gone_issues(self) -> None:
        """Raise the repair for an ended or withdrawn plan. Clear the one that no longer holds."""
        title = {"tariff": self.fuel.title}
        self._set_issue(ISSUE_PLAN_ENDED, title if self._gone == "ended" else None)
        self._set_issue(ISSUE_PLAN_WITHDRAWN, title if self._gone == "withdrawn" else None)

    def _check_freshness(self, data: TariffData) -> None:
        """Raise a repair when the plan is about to end or the store has not been reached for days.
        Each clears itself once the cause has gone."""
        if CONF_MANUAL in self.fuel.data:
            return
        now = dt_util.now()
        title = self.fuel.title
        ending = plan_ending(data, now.date())
        self._set_issue(
            ISSUE_PLAN_ENDING,
            None if ending is None else {"tariff": title, "date": ending.isoformat()},
        )
        unreached = days_unreached(data, now)
        self._set_issue(
            ISSUE_STORE_UNREACHED,
            None if unreached is None else {"tariff": title, "days": str(unreached)},
        )

    def _set_issue(self, key: str, placeholders: dict[str, str] | None) -> None:
        """Raise the repair with its text, or clear it when there are no placeholders."""
        issue = f"{key}_{self.fuel.subentry_id}"
        if placeholders is None:
            ir.async_delete_issue(self.hass, DOMAIN, issue)
            return
        ir.async_create_issue(
            self.hass, DOMAIN, issue, is_fixable=False, severity=ir.IssueSeverity.WARNING,
            translation_key=key, translation_placeholders=placeholders,
        )

    async def _read(self, today: date) -> TariffData:
        entry = self.fuel.data
        holidays_known = True
        is_holiday: Callable[[date], bool]
        if CONF_MANUAL in entry:  # the household's own rates: no store, and no public holidays
            definition = definition_from(entry[CONF_MANUAL], entry[CONF_NAME])
            is_holiday = no_holidays
            revisions = [Revision(today, definition)]
        else:
            definition = await self._access.async_definition(
                entry[CONF_COUNTRY], entry[CONF_PROVIDER], entry[CONF_TARIFF], today,
                area=entry[CONF_AREA],
            )
            try:
                is_holiday = await self._access.async_is_holiday(
                    entry[CONF_COUNTRY], definition.region
                )
            except StoreError:
                is_holiday, holidays_known = no_holidays, False
            revisions = [Revision(today, definition), *await self._later_revisions(today)]
        availability, reason = await self._country_status()
        names = tuple(dict.fromkeys(n for r in revisions for n in series_names(r.definition)))
        runs = await self._read_feeds(names, today)
        start, end = self._range(definition, today, feed=bool(names))
        try:
            slots = await self.hass.async_add_executor_job(
                price_timeline, revisions, start, end, runs, is_holiday
            )
        except StoreError:  # a year the store holds no holidays for
            holidays_known = False
            slots = await self.hass.async_add_executor_job(
                price_timeline, revisions, start, end, runs, no_holidays
            )
        return TariffData(
            definition, slots, holidays_known, is_holiday, tuple(revisions),
            tuple(feed_of(name) for name in names), end, self._read_time(), availability, reason,
        )

    async def _country_status(self) -> tuple[str | None, str | None]:
        """How complete the store says this country is, and why. Nothing for own rates."""
        if CONF_MANUAL in self.fuel.data:
            return None, None
        try:
            row = (await self._access.async_countries()).get(self.fuel.data[CONF_COUNTRY])
        except STORE_ERRORS:
            return None, None
        if not row:
            return None, None
        return row.get("availability"), reason_for(row, self.hass.config.language)

    def _read_time(self) -> datetime | None:
        """Now, unless the store was unreachable and the answer came from saved files: then the
        time of the last real read stays, so the age of the prices is not hidden."""
        if self._access.offline:
            return None if self.data is None else self.data.read_at
        return dt_util.utcnow()

    @staticmethod
    def _range(
        definition: TariffDefinition, today: date, *, feed: bool
    ) -> tuple[datetime, datetime]:
        midnight = datetime.min.time()
        past = timedelta(days=FEED_PAST_DAYS if feed else PAST_DAYS)
        ahead = timedelta(days=FEED_HORIZON_DAYS if feed else FIXED_HORIZON_DAYS)
        return (
            datetime.combine(today - past, midnight, definition.timezone),
            datetime.combine(today + ahead, midnight, definition.timezone),
        )

    async def _later_revisions(self, today: date) -> list[Revision]:
        """The revisions the store already holds that start after today, with their definitions.
        One that cannot be read ends the list, so a bad future file never hides today's prices."""
        entry = self.fuel.data
        found: list[Revision] = []
        try:
            starts = await self._access.async_revision_starts(
                entry[CONF_COUNTRY], entry[CONF_PROVIDER], entry[CONF_TARIFF], today,
                today + timedelta(days=REVISION_DAYS),
            )
            for first_day, _number in starts:
                later = await self._access.async_definition(
                    entry[CONF_COUNTRY], entry[CONF_PROVIDER], entry[CONF_TARIFF], first_day,
                    area=entry[CONF_AREA],
                )
                found.append(Revision(first_day, later))
        except STORE_ERRORS as err:
            _LOGGER.warning("A later revision of the tariff could not be read: %s", err)
        return found

    async def _read_feeds(
        self, names: tuple[str, ...], today: date
    ) -> dict[str, list[PriceSeries]]:
        """The runs of published prices for each series a tariff reads."""
        entry = self.fuel.data
        runs: dict[str, list[PriceSeries]] = {}
        for name in names:
            docs, _missing = await self._prices.async_days(
                entry[CONF_COUNTRY], feed_of(name), entry[CONF_AREA],
                today - timedelta(days=FEED_PAST_DAYS), today + timedelta(days=1),
            )
            runs[name] = series_runs(docs)
        self._check_published(names, runs)
        return runs

    def _check_published(self, names: tuple[str, ...], runs: dict[str, list[PriceSeries]]) -> None:
        """Raise a repair when tomorrow's prices are still missing late in the evening."""
        if not names:
            return
        now = dt_util.now()
        wanted = datetime.combine(
            now.date() + timedelta(days=FEED_HORIZON_DAYS), datetime.min.time(), now.tzinfo
        )
        held = all(found and found[-1].end >= wanted for found in runs.values())
        issue = f"{ISSUE_PRICES_LATE}_{self.fuel.subentry_id}"
        if held:
            ir.async_delete_issue(self.hass, DOMAIN, issue)
        elif now.hour >= PRICES_LATE_HOUR:
            ir.async_create_issue(
                self.hass, DOMAIN, issue, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_PRICES_LATE,
                translation_placeholders={"tariff": self.fuel.title},
            )
