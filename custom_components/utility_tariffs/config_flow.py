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
    DateSelector,
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
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util
from utility_tariffs_lib.tariffstore import StoreError

from .const import (
    BILL_MONTHS,
    CHEAP_BAND,
    CHEAP_RULES,
    CONF_AREA,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_DISCHARGE_ENERGY,
    CONF_BATTERY_SOC,
    CONF_BATTERY_WEAR,
    CONF_BILL_MONTHS,
    CONF_BILL_START_DAY,
    CONF_BILL_START_MONTH,
    CONF_CHEAP_RULE,
    CONF_CLEAR_CACHE,
    CONF_CONNECTED_LOAD,
    CONF_COUNTRY,
    CONF_ENTITY_KEY,
    CONF_EXPORT_ENERGY,
    CONF_HISTORY_START,
    CONF_HOUSE_ENERGY,
    CONF_IMPORT_ENERGY,
    CONF_MANUAL,
    CONF_MAX_METER_KW,
    CONF_NAME,
    CONF_PROVIDER,
    CONF_REFRESH_NOW,
    CONF_SERVICE,
    CONF_TARIFF,
    CONF_WINDOW_MINUTES,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
    MAX_BILL_START_DAY,
    MAX_WINDOW_MINUTES,
    MIN_WINDOW_MINUTES,
    SERVICE_ELECTRICITY,
    SERVICE_GAS,
    SERVICES,
    WINDOW_STEP_MINUTES,
)
from .country_reason import reason_for
from .energy_suggest import energy_dashboard_meters, gas_dashboard_meter
from .helper.store_access import TariffStoreAccess
from .manual import CountryDefaults, problem_with
from .manual_templates import BLANK, TEMPLATES, Template, timed_periods
from .store import store_access

OWN_RATES = "own_rates"  # the key of the first choice label in the translations
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


def _choices(plans: dict[str, _Plan], own_rates: str) -> dict[str, _Plan | None]:
    """Readable name to plan, own rates first. A name two plans share gets the plan id added."""
    ordered = sorted(plans.values(), key=lambda p: (p.provider_name, p.tariff_name))
    names = [f"{p.provider_name} \u2013 {p.tariff_name}" for p in ordered]
    choices: dict[str, _Plan | None] = {own_rates: None}
    for name, plan in zip(names, ordered, strict=True):
        choices[f"{name} ({plan.tariff})" if names.count(name) > 1 else name] = plan
    return choices


def _plan_schema(names: list[str], previous: dict[str, Any] | None) -> Any:
    """A searchable list. `custom_value` is what gives the frontend its search box."""
    selector = SelectSelector(
        SelectSelectorConfig(options=names, mode=SelectSelectorMode.DROPDOWN, custom_value=True)
    )
    default = (previous or {}).get(CONF_TARIFF)
    key = vol.Required(CONF_TARIFF, description={"suggested_value": default})
    return _schema({key: selector})


def _progress(step: int) -> dict[str, str]:
    """Which step this page is. The total is not known: the area page only follows some plans."""
    return {"step": str(step)}


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
        self._template: Template = TEMPLATES[BLANK]
        self._defaults = CountryDefaults("GB", "GBP")
        self._pending: tuple[str, str, dict[str, Any]] = ("", "", {})
        self._service = SERVICE_ELECTRICITY

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: the service. Reconfigure keeps the entry's own service and starts at the country."""
        if self.source == SOURCE_RECONFIGURE:
            self._service = self._get_reconfigure_entry().data.get(CONF_SERVICE, SERVICE_ELECTRICITY)
            return await self.async_step_country()
        taken = {
            entry.data.get(CONF_SERVICE, SERVICE_ELECTRICITY)
            for entry in self._async_current_entries()
        }
        free = [service for service in SERVICES if service not in taken]
        if not free:
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            self._service = user_input[CONF_SERVICE]
            return await self.async_step_country()
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(
                {
                    vol.Required(CONF_SERVICE, default=free[0]): SelectSelector(
                        SelectSelectorConfig(
                            options=free,
                            translation_key="service",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            last_step=False,
        )

    async def async_step_country(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2: the country. Own rates are the first choice on the next page."""
        access = store_access(self.hass, self._service)
        try:
            held = [code for code, row in (await access.async_countries()).items() if "path" in row]
        except STORE_ERRORS:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            self._chosen[CONF_COUNTRY] = user_input[CONF_COUNTRY]
            return await self.async_step_plan()
        return self.async_show_form(
            step_id="country",
            data_schema=self._country_schema(held),
            description_placeholders=_progress(2),
            last_step=False,
        )

    def _country_schema(self, held: list[str]) -> Any:
        """The country list, starting at the followed plan's country or else the home's."""
        current = self._reconfigure_country() or self.hass.config.country
        suggested = current if current in held else None
        return _schema(
            {
                vol.Required(CONF_COUNTRY, description={"suggested_value": suggested}): (
                    CountrySelector(CountrySelectorConfig(countries=held))
                )
            }
        )

    def _reconfigure_country(self) -> str | None:
        if self.source != SOURCE_RECONFIGURE:
            return None
        country = self._get_reconfigure_entry().data.get(CONF_COUNTRY)
        return country if isinstance(country, str) else None

    async def async_step_plan(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2: a searchable list of every plan in force today, own rates first.

        The list allows a typed value so that the frontend shows a search box. The value of a
        choice is its readable name, and anything that is not one of the names is refused.
        """
        access = store_access(self.hass, self._service)
        try:
            plans = await self._plans(access)
            note = await self._country_note(access)
        except STORE_ERRORS:
            return self.async_abort(reason="cannot_connect")
        if not plans:
            return self.async_abort(reason="no_tariffs")
        choices = _choices(plans, await self._own_rates_label())
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_TARIFF] in choices:
                return await self._take(choices[user_input[CONF_TARIFF]])
            errors["base"] = "unknown_plan"
        return self.async_show_form(
            step_id="plan",
            data_schema=_plan_schema(list(choices), user_input),
            description_placeholders={**_progress(3), "country_note": note},
            errors=errors,
        )

    async def _take(self, plan: _Plan | None) -> ConfigFlowResult:
        """Go on with the chosen plan, or to the own-rates form when none was chosen."""
        if plan is None:
            return await self.async_step_manual_template()
        self._chosen[CONF_PROVIDER], self._chosen[CONF_TARIFF] = plan.provider, plan.tariff
        self._names["provider"], self._names["tariff"] = plan.provider_name, plan.tariff_name
        return await self.async_step_area()

    async def _own_rates_label(self) -> str:
        """The first choice on the plan page, in the language of the home."""
        key = f"component.{DOMAIN}.selector.plan_choice.options.{OWN_RATES}"
        texts = await async_get_translations(
            self.hass, self.hass.config.language, "selector", [DOMAIN]
        )
        return texts.get(key, "Type in my own rates")

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
        reason = reason_for(row, self.hass.config.language)
        return f"\n\n**{self._chosen[CONF_COUNTRY]}:** {reason}" if reason else ""

    async def async_step_area(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 3, only for a plan that is priced by area."""
        access = store_access(self.hass, self._service)
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
                description_placeholders={
                    **_progress(4),
                    "plan": f"{self._names['provider']} {self._names['tariff']}",
                },
            )
        self._chosen[CONF_AREA] = user_input[CONF_AREA]
        suffix = "" if len(areas) == 1 else f" ({areas[user_input[CONF_AREA]]})"
        return await self._create(f"{self._names['provider']} {self._names['tariff']}{suffix}")

    async def async_step_manual_template(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The shape of a tariff that is not in the store. It only fills the next form."""
        if user_input is not None:
            self._template = TEMPLATES[user_input["template"]]
            self._defaults = await self._country_defaults()
            return await self.async_step_manual()
        return self.async_show_form(
            step_id="manual_template",
            data_schema=_schema({vol.Required("template", default=BLANK): _template_choice()}),
            last_step=False,
        )

    async def _country_defaults(self) -> CountryDefaults:
        """The chosen country with its currency and VAT from the store, or the home's own
        settings when the store has nothing for it or cannot be reached."""
        country = self._chosen.get(CONF_COUNTRY) or self.hass.config.country or "GB"
        currency, vat = self.hass.config.currency, None
        try:
            currency, vat = await store_access(self.hass, self._service).async_country_values(
                country, dt_util.now().date()
            )
        except STORE_ERRORS:
            pass  # the form still works from the home's settings
        return CountryDefaults(country, currency, float(vat) if vat else 0.0)

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The base rates of a tariff that is not in the store."""
        errors: dict[str, str] = {}
        if user_input is not None:
            typed = dict(user_input)
            timed = typed.pop("timed_rate", None)
            periods = timed_periods(self._template, timed)
            rates = {**typed, "timezone": self.hass.config.time_zone, "periods": periods}
            reason = problem_with(rates, user_input[CONF_NAME])
            if reason is None:
                self._manual = rates
                return await self.async_step_manual_more()
            errors["base"] = "invalid_tariff"
        return self.async_show_form(
            step_id="manual",
            data_schema=_manual_schema(user_input, self._template, self._defaults),
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
        unique = "manual" if self._service == SERVICE_ELECTRICITY else f"{self._service}/manual"
        return await self._finish(unique, title, {CONF_MANUAL: self._manual})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Follow a different plan. The entities keep their ids, history and place in dashboards."""
        return await self.async_step_user()

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The last page of a new entry: the bill dates and the meters, all optional.

        The meters are suggested from the Energy dashboard, so most homes only confirm them.
        """
        return await self._options_page("options", user_input)

    async def async_step_options_gas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The same page for gas: one meter and the bill dates, with gas wording."""
        return await self._options_page("options_gas", user_input)

    async def _options_page(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._save(*self._pending, options=_saved_setup(user_input))
        if self._service == SERVICE_GAS:
            suggested = await gas_dashboard_meter(self.hass)
            fields = {**_gas_meter_fields(suggested), **_bill_fields(suggested)}
        else:
            suggested = await energy_dashboard_meters(self.hass)
            fields = {**_meter_fields(suggested), **_bill_fields(suggested)}
        return self.async_show_form(step_id=step_id, data_schema=_schema(fields))

    async def _finish(self, unique: str, title: str, plan: dict[str, Any]) -> ConfigFlowResult:
        """Ask for the options when making a new entry. A plan change keeps what is set."""
        if self.source == SOURCE_RECONFIGURE:
            return await self._save(unique, title, plan)
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()
        self._pending = (unique, title, plan)
        if self._service == SERVICE_GAS:
            return await self.async_step_options_gas()
        return await self.async_step_options()

    def _service_data(self) -> dict[str, str]:
        """The service, written only when it is not the default so older entries read the same."""
        return {} if self._service == SERVICE_ELECTRICITY else {CONF_SERVICE: self._service}

    async def _create(self, title: str) -> ConfigFlowResult:
        unique = "/".join(
            self._chosen[key] for key in (CONF_COUNTRY, CONF_PROVIDER, CONF_TARIFF, CONF_AREA)
        )
        if self._service != SERVICE_ELECTRICITY:
            unique = f"{self._service}/{unique}"
        return await self._finish(unique, title, dict(self._chosen))

    async def _save(
        self, unique: str, title: str, plan: dict[str, Any], options: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
                data={**plan, **self._service_data(), CONF_NAME: title, CONF_ENTITY_KEY: key},
            )
        return self.async_create_entry(
            title=title,
            data={**plan, **self._service_data(), CONF_NAME: title, CONF_ENTITY_KEY: unique},
            options=options or {},
        )


def _template_choice() -> Any:
    return SelectSelector(
        SelectSelectorConfig(
            options=list(TEMPLATES), translation_key="manual_template", mode=SelectSelectorMode.LIST
        )
    )


def _manual_schema(
    previous: dict[str, Any] | None, template: Template, defaults: CountryDefaults
) -> Any:
    """The base rates. Country, currency and VAT start from the country's values in the store,
    and each price says which currency it is in."""
    given = previous or {}
    currency = given.get("currency", defaults.currency)

    def field(key: str, default: Any) -> Any:
        return vol.Required(key, default=given.get(key, default))

    def amount(unit: str | None = None, maximum: float | None = None) -> Any:
        if unit and not unit.startswith("%"):
            unit = f"{currency}/{unit.removeprefix('per ')}"
        config = NumberSelectorConfig(min=0, step="any", mode=NumberSelectorMode.BOX)
        if unit:
            config["unit_of_measurement"] = unit
        if maximum is not None:
            config["max"] = maximum
        return NumberSelector(config)

    return _schema(
        {
            field(CONF_NAME, "My tariff"): str,
            field("country", defaults.country): CountrySelector(),
            field("currency", defaults.currency): str,
            field("base_rate_name", template.base_name): str,
            field("base_rate", 0.0): amount("per kWh"),
            **_timed_field(template, amount),
            field("export_rate", 0.0): amount("per kWh"),
            field("standing_charge", 0.0): amount("per day"),
            field("levy", 0.0): amount("per month"),
            field("discount_rate", 0.0): amount("%", 100),
            field("vat_rate", defaults.vat_percent): amount("%", 100),
            field("vat_included", False): bool,
            field("bill_start_day", 1): NumberSelector(
                NumberSelectorConfig(min=1, max=28, step=1, mode=NumberSelectorMode.BOX)
            ),
        }
    )


def _timed_field(template: Template, amount: Any) -> dict[Any, Any]:
    """The price of the template's timed rate, when it has one."""
    if template.timed is None:
        return {}
    return {vol.Required("timed_rate", default=0.0): amount("per kWh")}


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
_NUMBERS = {
    CONF_BATTERY_CAPACITY: "kWh",
    CONF_BATTERY_WEAR: None,
    CONF_CONNECTED_LOAD: "kW",
    CONF_MAX_METER_KW: "kW",
}


class TariffOptionsFlow(OptionsFlowWithReload):
    """The window length, the energy meters to follow and the battery. Saving reloads the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._page("init", user_input)

    async def async_step_init_gas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The same page for gas, which has no export, battery or connected load."""
        return await self._page("init_gas", user_input)

    async def _page(self, step_id: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        if self.config_entry.data.get(CONF_SERVICE) == SERVICE_GAS:
            step_id = "init_gas"
        if user_input is not None:
            problem = await self._store_action(user_input)
            if problem is None:
                return self.async_create_entry(data=_saved(user_input))
            return self._form(step_id, self.config_entry.options, {"base": problem})
        return self._form(step_id, self.config_entry.options, {})

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

    def _form(self, step_id: str, options: Any, errors: dict[str, str]) -> ConfigFlowResult:
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
        fields[vol.Required(CONF_CHEAP_RULE, default=options.get(CONF_CHEAP_RULE, CHEAP_BAND))] = (
            SelectSelector(
                SelectSelectorConfig(options=list(CHEAP_RULES), translation_key="cheap_rule")
            )
        )
        fields.update(
            _gas_meter_fields(options) if step_id == "init_gas" else _meter_fields(options)
        )
        fields.update(_bill_fields(options))
        for key, unit in ({} if step_id == "init_gas" else _NUMBERS).items():
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
            step_id=step_id, data_schema=_schema(fields), errors=errors
        )


def _gas_meter_fields(options: Any) -> dict[Any, Any]:
    """Gas has one meter, what the home used, and no battery."""
    meter = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="energy"))
    return {
        vol.Optional(
            CONF_IMPORT_ENERGY, description={"suggested_value": options.get(CONF_IMPORT_ENERGY)}
        ): meter,
        vol.Optional(
            CONF_HISTORY_START, description={"suggested_value": options.get(CONF_HISTORY_START)}
        ): DateSelector(),
    }


def _meter_fields(options: Any) -> dict[Any, Any]:
    """The energy meters and the battery charge, each with its current value suggested."""
    meter = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="energy"))
    charge = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="battery"))
    fields: dict[Any, Any] = {
        vol.Optional(key, description={"suggested_value": options.get(key)}): meter
        for key in _METERS
    }
    fields[
        vol.Optional(
            CONF_HISTORY_START, description={"suggested_value": options.get(CONF_HISTORY_START)}
        )
    ] = DateSelector()
    fields[
        vol.Optional(
            CONF_BATTERY_SOC, description={"suggested_value": options.get(CONF_BATTERY_SOC)}
        )
    ] = charge
    return fields


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
    if user_input.get(CONF_CHEAP_RULE, CHEAP_BAND) != CHEAP_BAND:
        data[CONF_CHEAP_RULE] = user_input[CONF_CHEAP_RULE]  # the default is not stored
    data.update(_saved_setup(user_input))
    data.update({k: float(user_input[k]) for k in _NUMBERS if user_input.get(k) is not None})
    return data


def _saved_setup(user_input: dict[str, Any]) -> dict[str, Any]:
    """The meters, battery charge and bill dates that were filled in."""
    data: dict[str, Any] = {}
    data.update(
        {k: user_input[k] for k in (*_METERS, CONF_BATTERY_SOC, CONF_HISTORY_START) if user_input.get(k)}
    )
    data.update(
        {k: int(user_input[k]) for k in (CONF_BILL_START_DAY, CONF_BILL_MONTHS, CONF_BILL_START_MONTH)
         if user_input.get(k)}
    )
    return data
