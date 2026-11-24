"""Utility Tariffs: current tariff prices, windows and bills for Home Assistant."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any

from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .accountant import EnergyAccountant, MeterSetup
from .backfill import async_fill_history
from .const import (
    CONF_BATTERY_SOC,
    CONF_HISTORY_START,
    CONF_IMPORT_ENERGY,
    CONF_MAX_METER_KW,
    CONF_MOVED_TO,
    DEFAULT_MAX_METER_KW,
    DOMAIN,
    FUEL_TITLES,
    METER_TARGETS,
    hub_identifier,
)
from .coordinator import TariffConfigEntry, TariffCoordinator
from .energy_store import EnergyStore
from .fuel import Fuel
from .migrate import async_merge_entries
from .plan_ranker import PlanRanker
from .services import async_register_services

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_services(hass)
    await async_merge_entries(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TariffConfigEntry) -> bool:
    _async_tidy(hass, entry)
    coordinators: dict[str, TariffCoordinator] = {}
    for subentry_id in entry.subentries:
        coordinator = TariffCoordinator(hass, entry, subentry_id)
        await coordinator.async_config_entry_first_refresh()
        coordinators[subentry_id] = coordinator
        await _async_start_accounting(hass, entry, coordinator)
    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_fuels_changed))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TariffConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _async_tidy(hass: HomeAssistant, entry: TariffConfigEntry) -> None:
    """Undo what 1.5.0b4 and b5 added: the hub device, and a plan name as each tariff's title."""
    devices = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
        if (DOMAIN, hub_identifier(entry.entry_id)) in device.identifiers:
            devices.async_remove_device(device.id)
    for subentry in list(entry.subentries.values()):
        title = FUEL_TITLES.get(subentry.subentry_type)
        if title and subentry.title != title:
            hass.config_entries.async_update_subentry(entry, subentry, title=title)


async def _async_fuels_changed(hass: HomeAssistant, entry: TariffConfigEntry) -> None:
    """Reload when a fuel is added or removed. A change inside a fuel reloads from Configure."""
    if set(entry.subentries) == set(entry.runtime_data):
        return
    gone = [
        coordinator.fuel.store_key
        for subentry_id, coordinator in entry.runtime_data.items()
        if subentry_id not in entry.subentries
    ]
    await hass.config_entries.async_reload(entry.entry_id)
    for key in gone:  # after the reload, which saves the history once more as it unloads
        await EnergyStore(hass, key, dt_util.get_default_time_zone()).async_remove()


async def _async_start_accounting(
    hass: HomeAssistant, entry: TariffConfigEntry, coordinator: TariffCoordinator
) -> None:
    """Keep the energy history when the user has chosen a meter to follow."""
    fuel = coordinator.fuel
    meters = {
        key: fuel.options[key]
        for key in (*METER_TARGETS, CONF_BATTERY_SOC)
        if fuel.options.get(key)
    }
    if CONF_IMPORT_ENERGY not in meters:
        return
    store = EnergyStore(hass, fuel.store_key, coordinator.data.definition.timezone)
    accountant = EnergyAccountant(
        hass,
        store,
        MeterSetup(
            meters,
            float(fuel.options.get(CONF_MAX_METER_KW, DEFAULT_MAX_METER_KW)),
            _history_start(fuel),
        ),
        coordinator.async_update_listeners,
    )
    entry.async_on_unload(await accountant.async_start())
    entry.async_on_unload(store.async_save)
    entry.async_on_unload(accountant.clear_issue)
    coordinator.accountant = accountant
    coordinator.ranker = PlanRanker(coordinator)
    coordinator.ranker.async_start()
    entry.async_create_background_task(
        hass, _async_backfill(coordinator, accountant), "utility_tariffs backfill"
    )


def _history_start(fuel: Fuel) -> date | None:
    """The first day to fill from the meters' statistics, if the user chose one."""
    try:
        return date.fromisoformat(str(fuel.options[CONF_HISTORY_START]))
    except (KeyError, ValueError):
        return None


async def _async_backfill(coordinator: TariffCoordinator, accountant: EnergyAccountant) -> None:
    """Fill the history from the statistics, then price the plans again over what it now holds."""
    try:
        await async_fill_history(coordinator, accountant)
    except (OSError, ValueError, KeyError, TypeError) as err:
        _LOGGER.warning("The meter history could not be filled: %s", err)
    coordinator.async_update_listeners()


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> None:
    """Delete the saved energy history with the entry, unless it moved into another entry."""
    if entry.data.get(CONF_MOVED_TO):
        return
    zone = dt_util.get_default_time_zone()
    keys = [Fuel(entry, subentry_id).store_key for subentry_id in entry.subentries]
    for key in keys or [entry.entry_id]:  # an entry from before fuels were subentries
        await EnergyStore(hass, key, zone).async_remove()
