"""Choose a tariff from the open store: country, provider, plan and, where there is one, area."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    CountrySelector,
    CountrySelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)
from homeassistant.util import dt as dt_util
from utility_tariffs_lib.tariffstore import StoreError

from .const import (
    BILL_MONTHS,
    CONF_AREA,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_DISCHARGE_ENERGY,
    CONF_BATTERY_SOC,
    CONF_BATTERY_WEAR,
    CONF_BILL_MONTHS,
    CONF_BILL_START_DAY,
    CONF_BILL_START_MONTH,
    CONF_CLEAR_CACHE,
    CONF_COUNTRY,
    CONF_ENTITY_KEY,
    CONF_EXPORT_ENERGY,
    CONF_HOUSE_ENERGY,
    CONF_IMPORT_ENERGY,
    CONF_MANUAL,
    CONF_NAME,
    CONF_PROVIDER,
    CONF_REFRESH_NOW,
    CONF_TARIFF,
    CONF_WINDOW_MINUTES,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
    MAX_BILL_START_DAY,
    MAX_WINDOW_MINUTES,
    MIN_WINDOW_MINUTES,
    WINDOW_STEP_MINUTES,
)
from .helper.store_access import TariffStoreAccess
from .manual import problem_with
from .store import store_access

STORE_ERRORS = (StoreError, OSError, ValueError, KeyError, TypeError)
SINGLE_AREA = "all"


def _schema(fields: dict[Any, Any]) -> Any:
    # Typed as Any: Home Assistant 2026.10 types form schemas as probatio, while the minimum
    # supported release (2026.5) still builds them with voluptuous. Both accept either at run time.
    return vol.Schema(fields)


def _choice(key: str, options: dict[str, str]) -> Any:
    items = [SelectOptionDict(value=value, label=label) for value, label in options.items()]
    return _schema({vol.Required(key): SelectSelector(SelectSelectorConfig(options=items))})


@dataclass(frozen=True)
class _Plan:
    provider: str
    tariff: str
    provider_name: str
    tariff_name: str


def _progress(step: int, total: int) -> dict[str, str]:
    """Where the person is in the flow, for the page text."""
    return {"step": str(step), "total": str(total)}


class UtilityTariffsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Country, then supplier and plan together, then an area only where the plan has one."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TariffOptionsFlow:
        return TariffOptionsFlow()

    def __init__(self) -> None:
        self._chosen: dict[str, str] = {}
        self._names: dict[str, str] = {}
        self._manual: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a plan from the store, or type in the household's own rates."""
        if self.source != SOURCE_RECONFIGURE and self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_show_menu(step_id="user", menu_options=["store", "manual"])

    async def async_step_store(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: the country. The supplier and plan share the next page."""
        access = store_access(self.hass)
        try:
            held = [code for code, row in (await access.async_countries()).items() if "path" in row]
        except STORE_ERRORS:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            self._chosen[CONF_COUNTRY] = user_input[CONF_COUNTRY]
            return await self.async_step_plan()
        schema = _schema(
            {vol.Required(CONF_COUNTRY): CountrySelector(CountrySelectorConfig(countries=held))}
        )
        return self.async_show_form(
            step_id="store",
            data_schema=schema,
            description_placeholders=_progress(1, 2),
            last_step=False,
        )

    async def async_step_plan(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2: one list of every plan in force today, each named by supplier and plan."""
        access = store_access(self.hass)
        try:
            plans = await self._plans(access)
            note = await self._country_note(access)
        except STORE_ERRORS:
            return self.async_abort(reason="cannot_connect")
        if not plans:
            return self.async_abort(reason="no_tariffs")
        if user_input is not None:
            plan = plans[user_input[CONF_TARIFF]]
            self._chosen[CONF_PROVIDER], self._chosen[CONF_TARIFF] = plan.provider, plan.tariff
            self._names["provider"], self._names["tariff"] = plan.provider_name, plan.tariff_name
            return await self.async_step_area()
        options = [
            SelectOptionDict(value=key, label=f"{plan.provider_name} \u2013 {plan.tariff_name}")
            for key, plan in sorted(
                plans.items(), key=lambda item: (item[1].provider_name, item[1].tariff_name)
            )
        ]
        schema = _schema(
            {
                vol.Required(CONF_TARIFF): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(
            step_id="plan",
            data_schema=schema,
            description_placeholders={**_progress(2, 2), "country_note": note},
        )

    async def _plans(self, access: TariffStoreAccess) -> dict[str, _Plan]:
        """Plans with prices in force today, by `provider/tariff`."""
        today = dt_util.now().date()
        country = self._chosen[CONF_COUNTRY]
        plans: dict[str, _Plan] = {}
        for provider, provider_name in (await access.async_providers(country)).items():
            for tariff, name in (await access.async_tariffs(country, provider, today)).items():
                plans[f"{provider}/{tariff}"] = _Plan(provider, tariff, provider_name, name)
        return plans

    async def _country_note(self, access: TariffStoreAccess) -> str:
        """What the store says is missing for this country, as a read-only line. Empty if nothing."""
        row = (await access.async_countries()).get(self._chosen[CONF_COUNTRY], {})
        reason = row.get("reason")
        return f"\n\n**{self._chosen[CONF_COUNTRY]}:** {reason}" if reason else ""

    async def async_step_area(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 3, only for a plan that is priced by area."""
        access = store_access(self.hass)
        try:
            areas = await access.async_areas(
                self._chosen[CONF_COUNTRY],
                self._chosen[CONF_PROVIDER],
                self._chosen[CONF_TARIFF],
                dt_util.now().date(),
            )
        except STORE_ERRORS:
            return self.async_abort(reason="cannot_connect")
        if user_input is None and len(areas) == 1:
            user_input = {CONF_AREA: next(iter(areas))}
        if user_input is None:
            return self.async_show_form(
                step_id="area",
                data_schema=_choice(CONF_AREA, areas),
                description_placeholders=_progress(3, 3),
            )
        self._chosen[CONF_AREA] = user_input[CONF_AREA]
        suffix = "" if len(areas) == 1 else f" ({areas[user_input[CONF_AREA]]})"
        return await self._create(f"{self._names['provider']} {self._names['tariff']}{suffix}")

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The base rates of a tariff that is not in the store."""
        errors: dict[str, str] = {}
        if user_input is not None:
            rates = {**user_input, "timezone": self.hass.config.time_zone, "periods": []}
            reason = problem_with(rates, user_input[CONF_NAME])
            if reason is None:
                self._manual = rates
                return await self.async_step_manual_more()
            errors["base"] = "invalid_tariff"
        return self.async_show_form(
            step_id="manual",
            data_schema=_manual_schema(self.hass, user_input),
            errors=errors,
            last_step=False,
        )

    async def async_step_manual_more(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a timed rate such as a night rate, or finish."""
        return self.async_show_menu(step_id="manual_more", menu_options=["manual_period", "manual_done"])

    async def async_step_manual_period(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            period = {k: user_input[k] for k in ("name", "rate", "start", "end")}
            trial = {**self._manual, "periods": [*self._manual["periods"], period]}
            if user_input["start"] == user_input["end"]:
                errors["base"] = "empty_period"
            elif problem_with(trial, self._manual[CONF_NAME]) is not None:
                errors["base"] = "invalid_tariff"
            else:
                self._manual = trial
                return await self.async_step_manual_more()
        return self.async_show_form(
            step_id="manual_period",
            data_schema=_period_schema(user_input),
            errors=errors,
            last_step=False,
        )

    async def async_step_manual_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        title = self._manual[CONF_NAME]
        return await self._save("manual", title, {CONF_MANUAL: self._manual})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Follow a different plan. The entities keep their ids, history and place in dashboards."""
        return await self.async_step_user()

    async def _create(self, title: str) -> ConfigFlowResult:
        unique = "/".join(
            self._chosen[key] for key in (CONF_COUNTRY, CONF_PROVIDER, CONF_TARIFF, CONF_AREA)
        )
        return await self._save(unique, title, dict(self._chosen))

    async def _save(self, unique: str, title: str, plan: dict[str, Any]) -> ConfigFlowResult:
        """Make the entry, or on reconfigure move it to this plan and keep its entities."""
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            key = entry.data.get(CONF_ENTITY_KEY) or entry.unique_id or entry.entry_id
            return self.async_update_reload_and_abort(
                entry,
                unique_id=unique,
                title=title,
                data={**plan, CONF_NAME: title, CONF_ENTITY_KEY: key},
            )
        return self.async_create_entry(
            title=title, data={**plan, CONF_NAME: title, CONF_ENTITY_KEY: unique}
        )


def _manual_schema(hass: Any, previous: dict[str, Any] | None) -> Any:
    """The base rates. Currency and country start from the home's settings."""
    given = previous or {}

    def field(key: str, default: Any) -> Any:
        return vol.Required(key, default=given.get(key, default))

    def amount(unit: str | None = None, maximum: float | None = None) -> Any:
        config = NumberSelectorConfig(min=0, step="any", mode=NumberSelectorMode.BOX)
        if unit:
            config["unit_of_measurement"] = unit
        if maximum is not None:
            config["max"] = maximum
        return NumberSelector(config)

    return _schema(
        {
            field(CONF_NAME, "My tariff"): str,
            field("country", hass.config.country or "GB"): CountrySelector(),
            field("currency", hass.config.currency): str,
            field("base_rate_name", "Day"): str,
            field("base_rate", 0.0): amount("per kWh"),
            field("export_rate", 0.0): amount("per kWh"),
            field("standing_charge", 0.0): amount("per day"),
            field("levy", 0.0): amount("per month"),
            field("discount_rate", 0.0): amount("%", 100),
            field("vat_rate", 0.0): amount("%", 100),
            field("vat_included", False): bool,
            field("bill_start_day", 1): NumberSelector(
                NumberSelectorConfig(min=1, max=28, step=1, mode=NumberSelectorMode.BOX)
            ),
        }
    )


def _period_schema(previous: dict[str, Any] | None) -> Any:
    given = previous or {}
    return _schema(
        {
            vol.Required("name", default=given.get("name", "Night")): str,
            vol.Required("rate", default=given.get("rate", 0.0)): NumberSelector(
                NumberSelectorConfig(
                    min=0, step="any", mode=NumberSelectorMode.BOX, unit_of_measurement="per kWh"
                )
            ),
            vol.Required("start", default=given.get("start", "23:00:00")): TimeSelector(),
            vol.Required("end", default=given.get("end", "08:00:00")): TimeSelector(),
        }
    )


_METERS = (CONF_IMPORT_ENERGY, CONF_EXPORT_ENERGY, CONF_HOUSE_ENERGY, CONF_BATTERY_DISCHARGE_ENERGY)
_NUMBERS = {CONF_BATTERY_CAPACITY: "kWh", CONF_BATTERY_WEAR: None}


class TariffOptionsFlow(OptionsFlowWithReload):
    """The window length, the energy meters to follow and the battery. Saving reloads the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            problem = await self._store_action(user_input)
            if problem is None:
                return self.async_create_entry(data=_saved(user_input))
            return self._form(self.config_entry.options, {"base": problem})
        return self._form(self.config_entry.options, {})

    async def _store_action(self, user_input: dict[str, Any]) -> str | None:
        """Refresh or clear what was read from the store, if asked. Returns the error, if any."""
        clear = bool(user_input.get(CONF_CLEAR_CACHE))
        if not (clear or user_input.get(CONF_REFRESH_NOW)):
            return None
        coordinator = self.config_entry.runtime_data
        if clear and coordinator.access.offline:
            return "clear_while_offline"  # the files are all there is to run on
        await coordinator.async_refresh_store(clear=clear)
        return None

    def _form(self, options: Any, errors: dict[str, str]) -> ConfigFlowResult:
        current = options.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES)
        fields: dict[Any, Any] = {
            vol.Required(CONF_WINDOW_MINUTES, default=current): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_WINDOW_MINUTES,
                    max=MAX_WINDOW_MINUTES,
                    step=WINDOW_STEP_MINUTES,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            )
        }
        meter = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="energy"))
        for key in _METERS:
            fields[vol.Optional(key, description={"suggested_value": options.get(key)})] = meter
        charge = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="battery"))
        fields[
            vol.Optional(
                CONF_BATTERY_SOC, description={"suggested_value": options.get(CONF_BATTERY_SOC)}
            )
        ] = charge
        fields.update(_bill_fields(options))
        for key, unit in _NUMBERS.items():
            config = NumberSelectorConfig(min=0, step="any", mode=NumberSelectorMode.BOX)
            if unit:
                config["unit_of_measurement"] = unit
            fields[vol.Optional(key, description={"suggested_value": options.get(key)})] = (
                NumberSelector(config)
            )
        if CONF_MANUAL not in self.config_entry.data:
            fields[vol.Optional(CONF_REFRESH_NOW, default=False)] = bool
            fields[vol.Optional(CONF_CLEAR_CACHE, default=False)] = bool
        return self.async_show_form(
            step_id="init", data_schema=_schema(fields), errors=errors
        )


def _bill_fields(options: Any) -> dict[Any, Any]:
    """Where a bill starts and how long it runs. Left empty, the tariff's own dates apply."""
    day = NumberSelectorConfig(
        min=1, max=MAX_BILL_START_DAY, step=1, mode=NumberSelectorMode.BOX
    )
    month = NumberSelectorConfig(min=1, max=12, step=1, mode=NumberSelectorMode.BOX)
    lengths = [SelectOptionDict(value=str(n), label=str(n)) for n in BILL_MONTHS]
    suggested = options.get(CONF_BILL_MONTHS)
    return {
        vol.Optional(
            CONF_BILL_START_DAY, description={"suggested_value": options.get(CONF_BILL_START_DAY)}
        ): NumberSelector(day),
        vol.Optional(
            CONF_BILL_MONTHS,
            description={"suggested_value": None if suggested is None else str(suggested)},
        ): SelectSelector(SelectSelectorConfig(options=lengths)),
        vol.Optional(
            CONF_BILL_START_MONTH,
            description={"suggested_value": options.get(CONF_BILL_START_MONTH)},
        ): NumberSelector(month),
    }


def _saved(user_input: dict[str, Any]) -> dict[str, Any]:
    """The options to keep: the window, and every meter and battery setting that was filled in."""
    data: dict[str, Any] = {CONF_WINDOW_MINUTES: int(user_input[CONF_WINDOW_MINUTES])}
    data.update({k: user_input[k] for k in (*_METERS, CONF_BATTERY_SOC) if user_input.get(k)})
    data.update(
        {k: int(user_input[k]) for k in (CONF_BILL_START_DAY, CONF_BILL_MONTHS, CONF_BILL_START_MONTH)
         if user_input.get(k)}
    )
    data.update({k: float(user_input[k]) for k in _NUMBERS if user_input.get(k) is not None})
    return data
