"""The tariff store as this integration reads it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import (
    CACHE_FOLDERS,
    PRICE_CACHE_FOLDER,
    PRICE_STORE_URL,
    SERVICE_ELECTRICITY,
    STORE_URLS,
)
from .helper.store_access import PriceStoreAccess, TariffStoreAccess

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def store_access(hass: HomeAssistant, service: str = SERVICE_ELECTRICITY) -> TariffStoreAccess:
    """A reader of the open store with its cache under `.storage`. Tests replace this."""
    return TariffStoreAccess.for_home_assistant(
        hass, STORE_URLS[service], CACHE_FOLDERS[service]
    )


def price_access(hass: HomeAssistant) -> PriceStoreAccess:
    """A reader of the half-hourly prices with its cache under `.storage`. Tests replace this."""
    return PriceStoreAccess.for_home_assistant(hass, PRICE_STORE_URL, PRICE_CACHE_FOLDER)
