"""The device every sensor of one tariff sits on."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTITY_KEY, DEVICE_NAME, DOMAIN
from .coordinator import TariffCoordinator


class TariffEntity(CoordinatorEntity[TariffCoordinator]):
    """Base of the tariff's entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TariffCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        # The key is fixed when the entry is made. A plan chosen later changes the entry's unique
        # id but not this key, so the entities, their ids and their history stay as they were.
        stable = entry.data.get(CONF_ENTITY_KEY) or entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{stable}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, stable)},
            name=DEVICE_NAME,
            manufacturer=coordinator.data.definition.provider.name,
            model=coordinator.data.definition.name,
            entry_type=DeviceEntryType.SERVICE,
        )
