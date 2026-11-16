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

CONF_WINDOW_MINUTES = "window_minutes"  # length of the cheapest and dearest windows
DEFAULT_WINDOW_MINUTES = 120
MIN_WINDOW_MINUTES = 30
MAX_WINDOW_MINUTES = 720
WINDOW_STEP_MINUTES = 30

CONF_IMPORT_ENERGY = "import_energy_entity"  # the user's meter: kWh imported, only ever rising
CONF_EXPORT_ENERGY = "export_energy_entity"  # the user's meter: kWh exported, only ever rising
CONF_HOUSE_ENERGY = "house_energy_entity"  # the whole home's energy use, kWh only ever rising
CONF_BATTERY_DISCHARGE_ENERGY = "battery_discharge_energy_entity"  # kWh taken out of the battery
CONF_BATTERY_SOC = "battery_soc_entity"  # the battery's charge, in percent
CONF_BATTERY_CAPACITY = "battery_capacity_kwh"
CONF_BATTERY_WEAR = "battery_wear_per_kwh"  # what each kWh through the battery costs in wear

# The energy meters the history is built from, and the flow or load each one fills.
METER_TARGETS = {
    CONF_IMPORT_ENERGY: ("flows", "import"),
    CONF_EXPORT_ENERGY: ("flows", "export"),
    CONF_BATTERY_DISCHARGE_ENERGY: ("flows", "battery_discharge"),
    CONF_HOUSE_ENERGY: ("loads", "house"),
}
