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

from .const import DOMAIN
from .lib.tariff import WindowSearch, find_window

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import TariffConfigEntry

SERVICE_FIND_WINDOW = "find_window"
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
        latest_end=_aware(call.data.get("latest_end")),
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


def async_register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        SERVICE_FIND_WINDOW,
        _find_window,
        schema=FIND_WINDOW_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
