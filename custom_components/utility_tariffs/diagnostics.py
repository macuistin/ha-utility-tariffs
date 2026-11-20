"""What a bug report needs: the entry, the state of the held prices and the tariff in force."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_AREA, CONF_BATTERY_SOC, CONF_MANUAL, METER_TARGETS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import TariffConfigEntry

# The area is a coarse place, and the energy sensors are named by the household.
TO_REDACT = {CONF_AREA, CONF_BATTERY_SOC, *METER_TARGETS}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TariffConfigEntry
) -> dict[str, Any]:
    """The entry with the household's own details removed, and what the coordinator holds."""
    coordinator = entry.runtime_data
    data = coordinator.data
    held: dict[str, Any] = {"last_update_success": coordinator.last_update_success}
    if data is not None:
        definition = data.definition
        held |= {
            "tariff": definition.id,
            "revision": definition.revision,
            "provider": definition.provider.name,
            "currency": definition.currency,
            "timezone": definition.timezone_name,
            "own_rates": CONF_MANUAL in entry.data,
            "slots": len(data.slots),
            "first_slot": data.slots[0].start.isoformat() if data.slots else None,
            "last_slot": data.slots[-1].end.isoformat() if data.slots else None,
            "horizon_end": data.horizon_end.isoformat() if data.horizon_end else None,
            "price_feeds": list(data.feeds),
            "holidays_known": data.holidays_known,
            "revisions": len(data.revisions),
            "store_offline": coordinator.access.offline,
            "bill_kept": coordinator.accountant is not None,
            "meter_readings_left_out": (
                coordinator.accountant.excluded() if coordinator.accountant else []
            ),
        }
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator": held,
    }
