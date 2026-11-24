"""Move the entries of earlier versions into the single entry with a subentry for each fuel.

Before this, each followed fuel was a config entry of its own. Now one entry holds both, so the
integration page shows one hub with the two tariffs under it. The move keeps what the user sees:
entity ids and history (the entity key and the registry rows move, they are not made again), the
saved energy history (its key travels with the fuel) and the plan and options of each fuel.
"""

from __future__ import annotations

import asyncio
import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ENTITY_KEY,
    CONF_MOVED_TO,
    CONF_SERVICE,
    DOMAIN,
    HUB_NAME,
    SERVICE_ELECTRICITY,
)
from .fuel import CONF_STORE_KEY

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
ENTRY_VERSION = 2
MERGE_LOCK = f"{DOMAIN}_merge_lock"


def _service(entry: ConfigEntry[Any]) -> str:
    return str(entry.data.get(CONF_SERVICE, SERVICE_ELECTRICITY))


def fuel_settings(entry: ConfigEntry[Any]) -> dict[str, Any]:
    """What a fuel keeps: its plan and its options in one mapping, with the keys that must last."""
    return {
        **entry.data,
        **entry.options,
        CONF_SERVICE: _service(entry),
        CONF_ENTITY_KEY: entry.data.get(CONF_ENTITY_KEY) or entry.unique_id or entry.entry_id,
        CONF_STORE_KEY: entry.entry_id,
    }


def _earlier(hass: HomeAssistant) -> list[ConfigEntry[Any]]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.version < ENTRY_VERSION
    ]


async def async_merge_entries(hass: HomeAssistant) -> None:
    """Make one entry of every earlier one. Home Assistant may ask for it from several entries at
    once, so one merge runs at a time and the later ones find nothing left to do."""
    lock = hass.data.setdefault(MERGE_LOCK, asyncio.Lock())
    async with lock:
        earlier = _earlier(hass)
        if earlier:
            await _merge(hass, earlier)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> bool:
    """Home Assistant asks for the move when it sets up an entry of an earlier version."""
    await async_merge_entries(hass)
    return entry.version == ENTRY_VERSION


async def _merge(hass: HomeAssistant, earlier: list[ConfigEntry[Any]]) -> None:
    parent = next((e for e in earlier if _service(e) == SERVICE_ELECTRICITY), earlier[0])
    for entry in earlier:
        subentry = _add_subentry(hass, parent, entry)
        _move_registry(hass, entry, parent, subentry)
    hass.config_entries.async_update_entry(
        parent, data={}, options={}, title=HUB_NAME, unique_id=DOMAIN, version=ENTRY_VERSION
    )
    for entry in earlier:
        if entry is not parent:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_MOVED_TO: parent.entry_id}
            )
            await hass.config_entries.async_remove(entry.entry_id)
    _LOGGER.info("Moved %d tariff entries into one entry with a subentry each", len(earlier))


def _add_subentry(
    hass: HomeAssistant, parent: ConfigEntry[Any], entry: ConfigEntry[Any]
) -> ConfigSubentry:
    settings = fuel_settings(entry)
    subentry = ConfigSubentry(
        data=MappingProxyType(settings),
        subentry_type=_service(entry),
        title=entry.title,
        unique_id=entry.unique_id or str(settings[CONF_ENTITY_KEY]),
    )
    hass.config_entries.async_add_subentry(parent, subentry)
    return subentry


def _move_registry(
    hass: HomeAssistant, entry: ConfigEntry[Any], parent: ConfigEntry[Any], subentry: ConfigSubentry
) -> None:
    """Put the entry's devices and entities under the parent's subentry, keeping their ids."""
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
        devices.async_update_device(
            device.id,
            add_config_entry_id=parent.entry_id,
            add_config_subentry_id=subentry.subentry_id,
        )
        if entry is not parent:
            devices.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
        else:
            devices.async_update_device(
                device.id, remove_config_entry_id=parent.entry_id, remove_config_subentry_id=None
            )
    for item in er.async_entries_for_config_entry(entities, entry.entry_id):
        entities.async_update_entity(
            item.entity_id,
            config_entry_id=parent.entry_id,
            config_subentry_id=subentry.subentry_id,
        )
