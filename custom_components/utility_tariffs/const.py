"""Names shared across the integration."""

from __future__ import annotations

DOMAIN = "utility_tariffs"

# Where the open tariff store is read from: the raw files of its main branch, over https.
DEFAULT_STORE_URL = (
    "https://raw.githubusercontent.com/macuistin/utility-tariffs/main/tariffs/electricity"
)
CACHE_FOLDER = f"{DOMAIN}_store"

CONF_COUNTRY = "country"
CONF_PROVIDER = "provider"
CONF_TARIFF = "tariff"
CONF_AREA = "area"
CONF_NAME = "name"  # the title shown for the tariff, kept so a renamed plan does not rename it
