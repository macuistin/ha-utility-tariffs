"""Suggest the energy meters from the Energy dashboard, so setup needs only a confirmation."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_BATTERY_DISCHARGE_ENERGY, CONF_EXPORT_ENERGY, CONF_IMPORT_ENERGY


async def energy_dashboard_meters(hass: HomeAssistant) -> dict[str, str]:
    """The grid import and export, and battery discharge, meters the Energy dashboard uses.

    Empty when the dashboard is not set up. The first meter of each kind is taken. The whole
    home's use is not stored there, so it is never suggested.
    """
    sources = await _sources(hass)
    found: dict[str, str] = {}
    for source in sources:
        if source.get("type") == "grid":
            _first(found, CONF_IMPORT_ENERGY, source.get("flow_from"), "stat_energy_from")
            _first(found, CONF_EXPORT_ENERGY, source.get("flow_to"), "stat_energy_to")
        elif source.get("type") == "battery":
            found.setdefault(CONF_BATTERY_DISCHARGE_ENERGY, source.get("stat_energy_from", ""))
    return {key: value for key, value in found.items() if value}


async def gas_dashboard_meter(hass: HomeAssistant) -> dict[str, str]:
    """The Energy dashboard's gas meter, when it counts in kWh as the bill reads it."""
    for source in await _sources(hass):
        entity = source.get("stat_energy_from", "") if source.get("type") == "gas" else ""
        state = hass.states.get(entity) if entity else None
        if state is not None and state.attributes.get("unit_of_measurement") == "kWh":
            return {CONF_IMPORT_ENERGY: entity}
    return {}


async def _sources(hass: HomeAssistant) -> list[dict[str, Any]]:
    # Imported here so the tariff sensors work in a home without the energy integration.
    from homeassistant.components.energy.data import async_get_manager  # noqa: PLC0415

    manager = await async_get_manager(hass)
    saved: Any = manager.data or {}
    return list(saved.get("energy_sources", []))


def _first(found: dict[str, str], key: str, flows: Any, field: str) -> None:
    """Keep the first flow's meter for *key*."""
    if flows:
        found.setdefault(key, flows[0].get(field, ""))

