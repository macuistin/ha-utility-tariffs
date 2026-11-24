"""One price sensor for each rate band of the tariff, so an automation can read a band's price at
any time of day, not only the band in force now.

The price of a band is the engine's all-in price of one more kWh, from `marginal_prices`. It is
never read from the tariff file. The sensors follow the tariff: when a new revision adds a band
its sensor appears, and when a revision drops a band the sensor is removed, with no reload.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import DOMAIN, SERVICE_GAS
from .entity import AddEntities, TariffEntity
from .fuel import Fuel

if TYPE_CHECKING:
    from collections.abc import Mapping
    from decimal import Decimal

    from .coordinator import TariffCoordinator, TariffData

type Flow = Literal["import", "export"]
FLOWS: tuple[Flow, ...] = ("import", "export")
# A tariff with more bands than this has its band sensors off until the user enables them.
MAX_BANDS_ON_BY_DEFAULT = 3


def _prices(data: TariffData, flow: Flow) -> Mapping[str, Decimal]:
    marginal = data.marginal
    return marginal.import_prices if flow == "import" else marginal.export_prices


def band_names(data: TariffData, flow: Flow) -> list[str]:
    """The bands of *flow* the tariff in force prices, in the order the tariff lists them."""
    return list(_prices(data, flow))


def _key(flow: Flow, band: str) -> str:
    return f"{flow}_band_price_{slugify(band)}"


class BandPriceSensor(TariffEntity, SensorEntity):
    """The price of one more kWh in one band, in the tariff's currency."""

    _attr_suggested_display_precision = 4

    def __init__(self, coordinator: TariffCoordinator, flow: Flow, band: str) -> None:
        super().__init__(coordinator, _key(flow, band))
        self._flow: Flow = flow
        self._band = band
        self._attr_translation_key = f"{flow}_band_price"
        self._attr_translation_placeholders = {"band": band}
        self._attr_native_unit_of_measurement = f"{coordinator.data.definition.currency}/kWh"
        self._attr_entity_registry_enabled_default = (
            len(band_names(coordinator.data, flow)) <= MAX_BANDS_ON_BY_DEFAULT
        )

    @property
    def available(self) -> bool:
        return super().available and self._band in band_names(self.coordinator.data, self._flow)

    @property
    def native_value(self) -> float | None:
        price = _prices(self.coordinator.data, self._flow).get(self._band)
        return None if price is None else float(price)


def _unique_prefix(fuel: Fuel, flow: Flow) -> str:
    return f"{fuel.key}_{flow}_band_price_"


@callback
def async_setup_band_sensors(
    coordinator: TariffCoordinator, async_add_entities: AddEntities
) -> None:
    """Add a sensor for every band now, and keep them in step with the tariff afterwards."""
    added: set[tuple[Flow, str]] = set()

    @callback
    def sync() -> None:
        flows = ("import",) if coordinator.service == SERVICE_GAS else FLOWS
        wanted = {(flow, band) for flow in flows for band in band_names(coordinator.data, flow)}
        new = sorted(wanted - added)
        if new:
            added.update(new)
            async_add_entities(BandPriceSensor(coordinator, flow, band) for flow, band in new)
        _remove_dropped(coordinator, wanted)
        added.intersection_update(wanted)

    sync()
    coordinator.fuel.async_on_unload(coordinator.async_add_listener(sync))


def _remove_dropped(coordinator: TariffCoordinator, wanted: set[tuple[Flow, str]]) -> None:
    """Delete the registry entry of every band sensor whose band the tariff no longer prices."""
    fuel = coordinator.fuel
    registry = er.async_get(coordinator.hass)
    keep = {f"{_unique_prefix(fuel, flow)}{slugify(band)}" for flow, band in wanted}
    for item in er.async_entries_for_config_entry(registry, fuel.entry.entry_id):
        is_band = item.domain == "sensor" and item.platform == DOMAIN and any(
            (item.unique_id or "").startswith(_unique_prefix(fuel, flow)) for flow in FLOWS
        )
        if is_band and item.unique_id not in keep:
            registry.async_remove(item.entity_id)
