"""The share of the electricity imported that was used at cheap times, for a day, the bill period
and the last 30 days. Read from the half-hourly history, so a new plan shows it from the backfill.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.util import dt as dt_util

from .bill import bill_so_far
from .cheap_share import RATINGS, CheapShare, cheap_bands, cheap_share, share_rating
from .const import CHEAP_BAND, CHEAP_BELOW_AVERAGE, CONF_CHEAP_RULE
from .coordinator import TariffCoordinator
from .entity import TariffEntity

LAST_DAYS = 30


@dataclass(frozen=True, kw_only=True)
class CheapShareDescription(SensorEntityDescription):
    """A cheap share over one range of days, ending today."""

    first_day: Callable[[TariffCoordinator, date], date | None]


def _today(_coordinator: TariffCoordinator, today: date) -> date:
    return today


def _last_days(_coordinator: TariffCoordinator, today: date) -> date:
    return today - timedelta(days=LAST_DAYS - 1)


def _bill_period(coordinator: TariffCoordinator, today: date) -> date | None:
    accountant = coordinator.accountant
    if accountant is None:
        return None
    bill = bill_so_far(
        accountant.store.history,
        coordinator.data,
        coordinator.fuel.options,
        dt_util.now(),
    )
    return None if bill is None else bill.first_day


CHEAP_SHARE_SENSORS = (
    CheapShareDescription(
        key="cheap_share_today",
        translation_key="cheap_share_today",
        first_day=_today,
    ),
    CheapShareDescription(
        key="cheap_share_period",
        translation_key="cheap_share_period",
        first_day=_bill_period,
    ),
    CheapShareDescription(
        key="cheap_share_30_days",
        translation_key="cheap_share_30_days",
        first_day=_last_days,
        entity_registry_enabled_default=False,
    ),
)


def share_between(coordinator: TariffCoordinator, first: date, last: date) -> CheapShare | None:
    """The cheap share of the days from *first* to *last*, by the rule set in the options."""
    accountant = coordinator.accountant
    data = coordinator.data
    if accountant is None or data.on_a_feed:
        return None  # a feed has no bands, and its past prices are not held
    days = accountant.store.history.between(first, last)
    average = None
    if coordinator.fuel.options.get(CONF_CHEAP_RULE, CHEAP_BAND) == CHEAP_BELOW_AVERAGE:
        stats = data.day_stats(dt_util.now(), "import")
        if stats is None:
            return None
        average = stats.average
    cheap = cheap_bands(data.marginal.import_prices, average)
    return cheap_share(days, data.definition, data.is_holiday, cheap)


class CheapShareSensor(TariffEntity, SensorEntity):
    """Imported energy used in the tariff's cheapest band, as a share of all imported energy."""

    entity_description: CheapShareDescription
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: TariffCoordinator, description: CheapShareDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    def _share(self) -> CheapShare | None:
        """None when it cannot be worked out: no meter, or prices that come from a feed."""
        coordinator = self.coordinator
        today = dt_util.now().astimezone(coordinator.data.definition.timezone).date()
        first = self.entity_description.first_day(coordinator, today)
        return None if first is None else share_between(coordinator, first, today)

    @property
    def native_value(self) -> float | None:
        share = self._share()
        return None if share is None else round(share.percent, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        share = self._share()
        if share is None:
            return None
        return {
            "cheap_kwh": round(share.cheap_kwh, 3),
            "imported_kwh": round(share.total_kwh, 3),
        }


class CheapRatingSensor(TariffEntity, SensorEntity):
    """A label for today's cheap share: very good, good, average or poor."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(RATINGS)

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "cheap_use_rating")
        self._attr_translation_key = "cheap_use_rating"

    def _share(self) -> CheapShare | None:
        today = dt_util.now().astimezone(self.coordinator.data.definition.timezone).date()
        return share_between(self.coordinator, today, today)

    @property
    def native_value(self) -> str | None:
        """Unknown until something has been imported today, so an empty day is not 'poor'."""
        share = self._share()
        return None if share is None or share.total_kwh <= 0 else share_rating(share.percent)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        share = self._share()
        return None if share is None else {"cheap_share": round(share.percent, 1)}
