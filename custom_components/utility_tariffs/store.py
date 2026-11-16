"""The tariff store as this integration reads it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import CACHE_FOLDER, DEFAULT_STORE_URL
from .helper.store_access import TariffStoreAccess

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def store_access(hass: HomeAssistant) -> TariffStoreAccess:
    """A reader of the open store with its cache under `.storage`. Tests replace this."""
    return TariffStoreAccess.for_home_assistant(hass, DEFAULT_STORE_URL, CACHE_FOLDER)
