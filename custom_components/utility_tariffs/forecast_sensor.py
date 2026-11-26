"""The price forecast: prices known ahead, the next tariff change, the next low or high price."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.util import dt as dt_util
from utility_tariffs_lib.tariff import Revision

from .const import (
    CONF_HIGH_PERCENTILE,
    CONF_LOW_PERCENTILE,
    DEFAULT_HIGH_PERCENTILE,
    DEFAULT_LOW_PERCENTILE,
)
from .coordinator import TariffCoordinator, TariffData
from .entity import TariffEntity
from .forecast import (
    Percents,
    band_prices,
    history_points,
    level,
    next_cheap,
    next_dear,
    points_row,
    rate_rows,
    revision_rows,
    slot_rows,
    window_points,
)

LEVELS = ["low", "mid", "high"]


class PercentSensor(TariffEntity, SensorEntity):
    """A sensor that reads the low and high percentiles the user chose, live."""

    def percents(self) -> Percents:
        options = self.coordinator.fuel.options
        return Percents(
            int(options.get(CONF_LOW_PERCENTILE, DEFAULT_LOW_PERCENTILE)),
            int(options.get(CONF_HIGH_PERCENTILE, DEFAULT_HIGH_PERCENTILE)),
        )


def next_revision(data: TariffData, now: datetime) -> tuple[datetime, Revision] | None:
    """The first revision the store holds that starts after *now*, with its start."""
    for revision in data.revisions:
        start = datetime.combine(
            revision.first_day, datetime.min.time(), revision.definition.timezone
        )
        if start > now:
            return start, revision
    return None


class PriceForecastSensor(PercentSensor):
    """When the prices are known until, with the slots, the changes ahead and the percentiles."""

    _attr_translation_key = "price_forecast"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    # A day of half-hourly prices is long and changes every refresh, so it is not kept in the
    # history. The sensor's own state is the only part that is recorded.
    _unrecorded_attributes = frozenset({
        "slots", "import_rates", "export_rates", "changes", "window_percentiles",
        "history_percentiles",
    })

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "price_forecast")

    @property
    def native_value(self) -> datetime | None:
        data, now = self.coordinator.data, dt_util.now()
        if data.on_a_feed:
            return data.known_until(now)
        # A fixed tariff is priced a set time ahead, which says nothing about how long its
        # prices hold. They hold until the next revision, if the store has one.
        later = next_revision(data, now)
        return None if later is None else later[0]

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        data, now, percents = self.coordinator.data, dt_util.now(), self.percents()
        known = data.known_until(now)
        history = history_points(data, now, percents)
        return {
            "unit": f"{data.definition.currency}/kWh",
            "prices_fixed": not data.on_a_feed,
            "complete": known is not None and known >= (data.horizon_end or known),
            "slots": slot_rows(data, now),
            "import_rates": rate_rows(data, now, "import"),
            "export_rates": rate_rows(data, now, "export"),
            "changes": revision_rows(data, now),
            "window_percentiles": points_row(window_points(data, now, percents)),
            "history_percentiles": None if history is None else {
                **(points_row(history.points) or {}), "days": history.days,
            },
            "low_percentile": percents.low,
            "high_percentile": percents.high,
        }


class NextTariffChangeSensor(TariffEntity, SensorEntity):
    """The day the next revision the store holds starts, with the prices before and after."""

    _attr_translation_key = "next_tariff_change"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "next_tariff_change")

    def _later(self) -> tuple[datetime, Revision] | None:
        return next_revision(self.coordinator.data, dt_util.now())

    @property
    def native_value(self) -> datetime | None:
        later = self._later()
        return None if later is None else later[0]

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        later = self._later()
        if later is None:
            return {}
        return {
            "import_prices_before": band_prices(self.coordinator.data.definition),
            "import_prices_after": band_prices(later[1].definition),
        }


class PriceLevelSensor(PercentSensor):
    """Whether the price now is low, mid or high compared with other times."""

    _attr_translation_key = "price_level"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = LEVELS

    def __init__(self, coordinator: TariffCoordinator) -> None:
        super().__init__(coordinator, "price_level")

    @property
    def native_value(self) -> str | None:
        return level(self.coordinator.data, dt_util.now(), self.percents())

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        history = history_points(self.coordinator.data, dt_util.now(), self.percents())
        return {"basis": "history" if history else "forecast"}


class NextPeriodSensor(PercentSensor):
    """When the next low (or high) price starts, by the percentile the user chose."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: TariffCoordinator, *, high: bool) -> None:
        key = "next_high_price" if high else "next_low_price"
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._high = high

    def _found(self) -> dict[str, Any] | None:
        find = next_dear if self._high else next_cheap
        return find(self.coordinator.data, dt_util.now(), self.percents())

    @property
    def native_value(self) -> datetime | None:
        found = self._found()
        return None if found is None else found["start"]

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        found = self._found()
        if found is None:
            return {}
        return {
            "ends": found["end"].isoformat(),
            "price": float(found["price"]),
            "threshold": float(found["threshold"]),
            "percentile": self.percents().high if self._high else self.percents().low,
        }
