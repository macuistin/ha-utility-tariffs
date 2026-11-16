"""The device every sensor of one tariff sits on."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN
from .coordinator import TariffCoordinator


class TariffEntity(CoordinatorEntity[TariffCoordinator]):
    """Base of the tariff's entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TariffCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer=coordinator.data.definition.provider.name,
            model=coordinator.data.definition.name,
            entry_type=DeviceEntryType.SERVICE,
        )
