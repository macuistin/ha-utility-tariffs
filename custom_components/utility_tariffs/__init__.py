"""Utility Tariffs: current tariff prices, windows and bills for Home Assistant."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.util import dt as dt_util

from .accountant import EnergyAccountant, MeterSetup
from .const import (
    CONF_BATTERY_SOC,
    CONF_HISTORY_START,
    CONF_IMPORT_ENERGY,
    CONF_MAX_METER_KW,
    DEFAULT_MAX_METER_KW,
    METER_TARGETS,
)
from .coordinator import TariffConfigEntry, TariffCoordinator
from .energy_store import EnergyStore
from .plan_ranker import PlanRanker
from .services import async_register_services

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR]


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
    accountant = EnergyAccountant(
        hass,
        store,
        MeterSetup(
            meters,
            float(entry.options.get(CONF_MAX_METER_KW, DEFAULT_MAX_METER_KW)),
            _history_start(entry),
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


def _history_start(entry: TariffConfigEntry) -> date | None:
    """The first day to fill from the meters' statistics, if the user chose one."""
    try:
        return date.fromisoformat(str(entry.options[CONF_HISTORY_START]))
    except (KeyError, ValueError):
        return None


async def _async_backfill(coordinator: TariffCoordinator, accountant: EnergyAccountant) -> None:
    """Fill the history from the statistics, then price the plans again over what it now holds."""
    try:
        result = await accountant.async_backfill()
        if result.slots and coordinator.ranker is not None:
            await coordinator.ranker.async_refresh(dt_util.now().date())
    except (OSError, ValueError, KeyError, TypeError) as err:
        _LOGGER.warning("The meter history could not be filled: %s", err)
    coordinator.async_update_listeners()


async def async_remove_entry(hass: HomeAssistant, entry: TariffConfigEntry) -> None:
    """Delete the saved energy history with the plan."""
    await EnergyStore(hass, entry.entry_id, dt_util.get_default_time_zone()).async_remove()
