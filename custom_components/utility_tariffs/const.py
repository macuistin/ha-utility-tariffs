"""Names shared across the integration."""

from __future__ import annotations

DOMAIN = "utility_tariffs"

# The device is always called this, so entity ids read sensor.utility_tariff_<thing>.
DEVICE_NAME = "Utility Tariff"

# Where the open tariff store is read from: the raw files of its main branch, over https.
DEFAULT_STORE_URL = (
    "https://raw.githubusercontent.com/macuistin/utility-tariffs/main/tariffs/electricity"
)
CACHE_FOLDER = f"{DOMAIN}_store"
# The half-hourly prices of a dynamic tariff, from the store's `prices` branch.
PRICE_STORE_URL = "https://raw.githubusercontent.com/macuistin/utility-tariffs/prices"
PRICE_CACHE_FOLDER = f"{DOMAIN}_prices"

CONF_COUNTRY = "country"
CONF_PROVIDER = "provider"
CONF_TARIFF = "tariff"
CONF_AREA = "area"
CONF_ENTITY_KEY = "entity_key"  # fixed when the entry is made, so a new plan keeps its entities
CONF_MANUAL = "manual"  # the household's own rates, held in the entry, not read from the store
CONF_NAME = "name"  # the title shown for the tariff, kept so a renamed plan does not rename it

# Where a bill period starts and how long it runs. Unset, the tariff's own dates are used.
CONF_BILL_START_DAY = "bill_start_day"  # day of the month a bill starts, 1 to 28
CONF_BILL_MONTHS = "bill_months"  # calendar months in one bill: 1, 2, 3, 4, 6 or 12
CONF_BILL_START_MONTH = "bill_start_month"  # a month a bill starts in, so two-month bills line up
BILL_MONTHS = (1, 2, 3, 4, 6, 12)  # the lengths that divide a year
MAX_BILL_START_DAY = 28

# Actions in the options form, never saved: read the store again now, or delete the saved files.
CONF_REFRESH_NOW = "refresh_now"
CONF_OWN_RATES = "own_rates"  # setup only: a ticked box on the first page, never stored
CONF_CLEAR_CACHE = "clear_cache"

CONF_WINDOW_MINUTES = "window_minutes"  # length of the cheapest and dearest windows
DEFAULT_WINDOW_MINUTES = 120
MIN_WINDOW_MINUTES = 30
MAX_WINDOW_MINUTES = 720
WINDOW_STEP_MINUTES = 30

# What counts as a low and a high price: a price at or below the low percentile of the prices
# known, or at or above the high one. Changed live from number entities, no reload.
CONF_LOW_PERCENTILE = "low_percentile"
CONF_HIGH_PERCENTILE = "high_percentile"
DEFAULT_LOW_PERCENTILE = 10
DEFAULT_HIGH_PERCENTILE = 90
MAX_LOW_PERCENTILE = 49
MIN_HIGH_PERCENTILE = 51

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
