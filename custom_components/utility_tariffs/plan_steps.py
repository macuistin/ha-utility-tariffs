"""The pages that choose a plan, shared by setup and Configure: country, plan, area, own rates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowContext, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowHandler
from homeassistant.helpers.selector import (
    CountrySelector,
    CountrySelectorConfig,
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
    CONF_AREA,
    CONF_COUNTRY,
    CONF_ENTITY_KEY,
    CONF_MANUAL,
    CONF_NAME,
    CONF_PROVIDER,
    CONF_SERVICE,
    CONF_TARIFF,
    DOMAIN,
    SERVICE_ELECTRICITY,
)
from .country_reason import reason_for
from .helper.store_access import TariffStoreAccess
from .manual import HOLIDAY_RULES, WEEKDAYS, CountryDefaults, problem_with
from .manual_templates import BLANK, TEMPLATES, Template, timed_periods
from .store import store_access

# What a plan stores, replaced when the plan changes. The rest of a fuel's settings is kept.
PLAN_KEYS = (CONF_COUNTRY, CONF_PROVIDER, CONF_TARIFF, CONF_AREA, CONF_MANUAL, CONF_NAME)
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


def service_data(service: str) -> dict[str, str]:
    """The service, written only when it is not the default so older entries read the same."""
    return {} if service == SERVICE_ELECTRICITY else {CONF_SERVICE: service}


def entry_data(plan: dict[str, Any], service: str, title: str, key: str) -> dict[str, Any]:
    """What an entry stores for a plan. The key fixes its entity ids, so a new plan keeps them."""
    return {**plan, **service_data(service), CONF_NAME: title, CONF_ENTITY_KEY: key}


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


class PlanSteps(FlowHandler[ConfigFlowContext, ConfigFlowResult, str]):
    """Country, supplier and plan together, an area where the plan has one, or own rates.

    Setup and Configure both mix this in. Each says what to do with the chosen plan in
    `_plan_ready`, and which country the plan list starts at in `_current_country`.
    """

    hass: HomeAssistant

    def __init__(self) -> None:
        self._service = SERVICE_ELECTRICITY
        self._reset_pick()

    def _reset_pick(self) -> None:
        self._chosen: dict[str, str] = {}
        self._names: dict[str, str] = {}
        self._manual: dict[str, Any] = {}
        self._template: Template = TEMPLATES[BLANK]
        self._defaults = CountryDefaults("GB", "GBP")

    def _current_country(self) -> str | None:
        """The country the list starts at, or None to start at the home's own."""
        return None

    async def _plan_ready(self, unique: str, title: str, plan: dict[str, Any]) -> ConfigFlowResult:
        raise NotImplementedError

    async def async_step_country(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
        current = self._current_country() or self.hass.config.country
        suggested = current if current in held else None
        return _schema(
            {
                vol.Required(CONF_COUNTRY, description={"suggested_value": suggested}): (
                    CountrySelector(CountrySelectorConfig(countries=held))
                )
            }
        )

    async def async_step_plan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
        """What the store says is missing for this country, as a read-only line, or empty."""
        row = (await access.async_countries()).get(self._chosen[CONF_COUNTRY], {})
        reason = reason_for(row, self.hass.config.language)
        return f"\n\n**{self._chosen[CONF_COUNTRY]}:** {reason}" if reason else ""

    async def async_step_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
        title = f"{self._names['provider']} {self._names['tariff']}{suffix}"
        unique = "/".join(
            self._chosen[key] for key in (CONF_COUNTRY, CONF_PROVIDER, CONF_TARIFF, CONF_AREA)
        )
        if self._service != SERVICE_ELECTRICITY:
            unique = f"{self._service}/{unique}"
        return await self._plan_ready(unique, title, dict(self._chosen))

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

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
        return self.async_show_menu(
            step_id="manual_more", menu_options=["manual_period", "manual_done"]
        )

    async def async_step_manual_period(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            period = {k: v for k, v in user_input.items() if v not in ("", [], None)}
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
        return await self._plan_ready(unique, title, {CONF_MANUAL: self._manual})


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
            vol.Optional("days", default=given.get("days", [])): SelectSelector(
                SelectSelectorConfig(
                    options=list(WEEKDAYS), multiple=True, translation_key="weekday",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required("holidays", default=given.get("holidays", "normal")): SelectSelector(
                SelectSelectorConfig(
                    options=list(HOLIDAY_RULES), translation_key="holiday_rule",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )
