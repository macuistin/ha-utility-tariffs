"""Service actions. They return their answer, so an automation can use it in a template."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .bill import bill_so_far
from .bill_summary import render_bill_html
from .const import CONF_NAME, DOMAIN
from .lib.tariff import WindowSearch, find_window
from .windows import end_of_tomorrow

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import TariffConfigEntry

SERVICE_FIND_WINDOW = "find_window"
SERVICE_GET_PRICES = "get_prices"
SERVICE_BILL_SUMMARY = "bill_summary"
ATTR_ENTRY = "config_entry_id"
FLOWS = ("import", "export")

FIND_WINDOW_SCHEMA: Any = vol.Schema(
    {
        vol.Required(ATTR_ENTRY): cv.string,
        vol.Required("duration"): vol.All(cv.time_period, vol.Range(min=timedelta(minutes=1))),
        vol.Optional("flow", default="import"): vol.In(FLOWS),
        vol.Optional("highest", default=False): cv.boolean,
        vol.Optional("power_kw", default=1.0): vol.All(vol.Coerce(float), vol.Range(min=0.001)),
        vol.Optional("earliest_start"): cv.datetime,
        vol.Optional("latest_end"): cv.datetime,
    }
)

GET_PRICES_SCHEMA: Any = vol.Schema(
    {
        vol.Required(ATTR_ENTRY): cv.string,
        vol.Optional("start"): cv.datetime,
        vol.Optional("end"): cv.datetime,
    }
)


BILL_SUMMARY_SCHEMA: Any = vol.Schema({vol.Required(ATTR_ENTRY): cv.string})


def _entry(hass: HomeAssistant, entry_id: str) -> TariffConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_entry",
            translation_placeholders={"entry": entry_id},
        )
    if not hasattr(entry, "runtime_data"):
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    return entry


def _aware(value: datetime | None) -> datetime | None:
    """A time the user typed in Home Assistant's time zone, unless it names its own."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=dt_util.get_default_time_zone())


async def _find_window(call: ServiceCall) -> ServiceResponse:
    entry = _entry(call.hass, call.data[ATTR_ENTRY])
    data = entry.runtime_data.data
    search = WindowSearch(
        duration=call.data["duration"],
        flow=call.data["flow"],
        highest=call.data["highest"],
        power_kw=Decimal(str(call.data["power_kw"])),
        earliest_start=_aware(call.data.get("earliest_start")) or dt_util.now(),
        latest_end=_aware(call.data.get("latest_end")) or end_of_tomorrow(data, dt_util.now()),
    )
    window = await call.hass.async_add_executor_job(find_window, data.slots, search)
    if window is None:
        return {"found": False}
    return {
        "found": True,
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "cost": float(window.cost),
        "average_price": float(window.average_price),
        "saving": None if window.saving is None else float(window.saving),
        "complete": window.complete,
        "currency": data.definition.currency,
    }


async def _get_prices(call: ServiceCall) -> ServiceResponse:
    """The held prices that overlap the range, cut to it. Defaults to the next 24 hours."""
    entry = _entry(call.hass, call.data[ATTR_ENTRY])
    data = entry.runtime_data.data
    start = _aware(call.data.get("start")) or dt_util.now()
    end = _aware(call.data.get("end")) or start + timedelta(days=1)
    if end <= start:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="end_before_start")
    slots = [slot for slot in data.slots if slot.end > start and slot.start < end]
    covered = bool(slots) and slots[0].start <= start and slots[-1].end >= end
    known = data.known_until(start)
    return {
        "currency": data.definition.currency,
        "unit": f"{data.definition.currency}/kWh",
        "complete": covered,
        "known_until": None if known is None else known.isoformat(),
        "holidays_known": data.holidays_known,
        "prices": [
            {
                "start": max(slot.start, start).isoformat(),
                "end": min(slot.end, end).isoformat(),
                "import_price": float(slot.import_price),
                "export_price": float(slot.export_price),
                "import_band": slot.import_band,
                "export_band": slot.export_band,
                "source": slot.source,
            }
            for slot in slots
        ],
    }


async def _bill_summary(call: ServiceCall) -> ServiceResponse:
    """The bill so far as an HTML page, with its total and period."""
    entry = _entry(call.hass, call.data[ATTR_ENTRY])
    coordinator = entry.runtime_data
    accountant = coordinator.accountant
    if accountant is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_meter")
    data = coordinator.data
    bill = bill_so_far(accountant.store.history, data, entry.options, dt_util.now())
    return {
        "html": render_bill_html(bill, data.definition, entry.data[CONF_NAME]),
        "total": float(bill.priced.total),
        "currency": data.definition.currency,
        "period_start": bill.first_day.isoformat(),
        "next_period_start": bill.next_first_day.isoformat(),
        "days_priced": bill.days,
        "days_in_period": bill.period_days,
    }


def async_register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        SERVICE_FIND_WINDOW,
        _find_window,
        schema=FIND_WINDOW_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PRICES,
        _get_prices,
        schema=GET_PRICES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_BILL_SUMMARY,
        _bill_summary,
        schema=BILL_SUMMARY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
