"""Utility Tariffs: current tariff prices, windows and bills for Home Assistant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.util import dt as dt_util

from .accountant import EnergyAccountant
from .const import CONF_BATTERY_SOC, CONF_IMPORT_ENERGY, METER_TARGETS
from .coordinator import TariffConfigEntry, TariffCoordinator
from .energy_store import EnergyStore
from .services import async_register_services

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TariffConfigEntry) -> bool:
    coordinator = TariffCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await _async_start_accounting(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TariffConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_start_accounting(
    hass: HomeAssistant, entry: TariffConfigEntry, coordinator: TariffCoordinator
) -> None:
    """Keep the energy history when the user has chosen a meter to follow."""
    meters = {
        key: entry.options[key]
        for key in (*METER_TARGETS, CONF_BATTERY_SOC)
        if entry.options.get(key)
    }
    if CONF_IMPORT_ENERGY not in meters:
        return
    store = EnergyStore(hass, entry.entry_id, coordinator.data.definition.timezone)
    accountant = EnergyAccountant(hass, store, meters, coordinator.async_update_listeners)
    entry.async_on_unload(await accountant.async_start())
    entry.async_on_unload(store.async_save)
    coordinator.accountant = accountant


async def async_remove_entry(hass: HomeAssistant, entry: TariffConfigEntry) -> None:
    """Delete the saved energy history with the plan."""
    await EnergyStore(hass, entry.entry_id, dt_util.get_default_time_zone()).async_remove()
