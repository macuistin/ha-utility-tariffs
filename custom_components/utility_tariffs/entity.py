"""The device every sensor of one tariff sits on."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTITY_KEY, DEVICE_NAMES, DOMAIN, SERVICE_GAS
from .coordinator import TariffCoordinator

GAS_NAMES = frozenset(
    {
        "gas_average_import_price_today",
        "gas_average_import_price_tomorrow",
        "gas_cheap_share_30_days",
        "gas_cheap_share_period",
        "gas_cheap_share_today",
        "gas_cheap_use_rating",
        "gas_highest_import_price_today",
        "gas_highest_import_price_tomorrow",
        "gas_highest_price_time_today",
        "gas_highest_price_time_tomorrow",
        "gas_import_band",
        "gas_import_band_price",
        "gas_import_price",
        "gas_import_price_percent_of_highest",
        "gas_import_price_rating",
        "gas_lowest_import_price_today",
        "gas_lowest_import_price_tomorrow",
        "gas_lowest_price_time_today",
        "gas_lowest_price_time_tomorrow",
        "gas_next_import_price",
        "gas_period_import",
        "gas_previous_import_price",
    }
)


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
            name=DEVICE_NAMES[coordinator.service],
            manufacturer=coordinator.data.definition.provider.name,
            model=coordinator.data.definition.name,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def translation_key(self) -> str | None:
        """A gas entry says gas where the electricity name says import or electricity.

        The key is the same for both, so the entity ids of an electricity entry do not change.
        """
        key = super().translation_key
        if key and self.coordinator.service == SERVICE_GAS and f"gas_{key}" in GAS_NAMES:
            return f"gas_{key}"
        return key
