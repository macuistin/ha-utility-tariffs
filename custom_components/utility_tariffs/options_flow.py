"""Configure: a menu of pages, each opened, changed and returned from, and saved together.

  init        the menu: Tariff, Meters, Battery, Bills, Cheap windows, Tariff store, Add a fuel,
              each with a line on what is set now, and Save changes once something has changed
  tariff      choose a different plan, through the same pages as setup (country, plan, area or
              own rates)
  meters, battery, bills, windows, store    one topic each, gas has its own meters page

Nothing is written until Save changes. The pages keep their answers on the flow, and a plan
change, a new fuel and the options are applied together in `async_step_confirm`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    CHEAP_BAND,
    CHEAP_RULES,
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
    CONF_EXPORT_ENERGY,
    CONF_HISTORY_START,
    CONF_HOUSE_ENERGY,
    CONF_IMPORT_ENERGY,
    CONF_MANUAL,
    CONF_MAX_METER_KW,
    CONF_REFRESH_NOW,
    CONF_SERVICE,
    CONF_WINDOW_MINUTES,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
    MAX_WINDOW_MINUTES,
    MIN_WINDOW_MINUTES,
    SERVICE_ELECTRICITY,
    SERVICE_GAS,
    WINDOW_STEP_MINUTES,
)
from .energy_suggest import energy_dashboard_meters, gas_dashboard_meter
from .option_fields import (
    _bill_fields,
    _gas_meter_fields,
    _meter_fields,
    _saved_setup,
)
from .options_summary import (
    battery_line,
    bills_line,
    meters_line,
    tariff_line,
    windows_line,
)
from .plan_steps import PlanSteps, _schema, entry_data

_INTS = (CONF_WINDOW_MINUTES, CONF_BILL_START_DAY, CONF_BILL_MONTHS, CONF_BILL_START_MONTH)
_FLOATS = (CONF_BATTERY_CAPACITY, CONF_BATTERY_WEAR, CONF_CONNECTED_LOAD, CONF_MAX_METER_KW)

_METER_KEYS = (CONF_IMPORT_ENERGY, CONF_EXPORT_ENERGY, CONF_HOUSE_ENERGY, CONF_HISTORY_START)
_GAS_METER_KEYS = (CONF_IMPORT_ENERGY, CONF_HISTORY_START)
_BATTERY_KEYS = (
    CONF_BATTERY_DISCHARGE_ENERGY,
    CONF_BATTERY_SOC,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_WEAR,
)
_BILL_KEYS = (CONF_BILL_START_DAY, CONF_BILL_MONTHS, CONF_BILL_START_MONTH, CONF_CONNECTED_LOAD)
_WINDOW_KEYS = (CONF_WINDOW_MINUTES, CONF_CHEAP_RULE)


@dataclass
class _StagedPlan:
    unique: str
    title: str
    data: dict[str, Any]


@dataclass
class _NewFuel:
    service: str
    plan: _StagedPlan
    options: dict[str, Any]


def _clean(key: str, raw: Any) -> Any:
    """The value to keep for a field, or None to leave the option out."""
    if key == CONF_WINDOW_MINUTES:
        return int(raw)
    if key == CONF_CHEAP_RULE:
        return None if raw in (None, CHEAP_BAND) else raw
    if key in _FLOATS:
        return None if raw is None else float(raw)
    if key in _INTS:
        return int(raw) if raw else None
    return raw or None


def _number(unit: str | None = None) -> Any:
    config = NumberSelectorConfig(min=0, step="any", mode=NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _suggest(key: str, options: Any) -> Any:
    return vol.Optional(key, description={"suggested_value": options.get(key)})


class TariffOptionsFlow(PlanSteps, OptionsFlow):
    """Pages for one entry. Saving reloads the entry once, whatever was changed."""

    def __init__(self) -> None:
        super().__init__()
        self._changes: dict[str, Any] = {}
        self._other_changes: dict[str, dict[str, Any]] = {}  # the other followed fuel's options
        self._new_plans: dict[str, _StagedPlan] = {}  # a new plan for each fuel already followed
        self._new_fuel: _NewFuel | None = None
        self._adding = False
        self._refresh = False
        self._clear = False

    # -- what the entry is and what would change -------------------------------------------------

    def _own_service(self) -> str:
        return str(self.config_entry.data.get(CONF_SERVICE, SERVICE_ELECTRICITY))

    def _effective(self) -> dict[str, Any]:
        """The saved options with the changes made so far."""
        merged = dict(self.config_entry.options)
        for key, value in self._changes.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        return merged

    def _dirty(self) -> bool:
        return bool(
            self._new_plans
            or any(self._other_changes.values())
            or self._new_fuel
            or self._refresh
            or self._clear
            or self._effective() != dict(self.config_entry.options)
        )

    def _current_country(self) -> str | None:
        country = self.config_entry.data.get("country")
        return country if isinstance(country, str) else None

    def _entry_for(self, service: str) -> ConfigEntry | None:
        """The entry that follows this fuel, or None when it is not followed yet."""
        if service == self._own_service():
            return self.config_entry
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_SERVICE, SERVICE_ELECTRICITY) == service:
                return entry
        return None

    def _tariff_line(self, service: str) -> str:
        """What the Electricity tariff and Gas tariff rows say: the plan now, or the one chosen."""
        entry = self._entry_for(service)
        if entry is None:
            if self._new_fuel and self._new_fuel.service == service:
                return f"{self._new_fuel.plan.title} is added when you save"
            return f"not followed yet, choose a {service} plan"
        staged = self._new_plans.get(service)
        line = tariff_line(entry.title, entry.data, staged.title if staged else None)
        options = self._options_of(service)
        if options.get(CONF_BILL_START_DAY) or options.get(CONF_BILL_MONTHS):
            line += f", {bills_line(options)}"
        return line

    def _stage(self, keys: tuple[str, ...], user_input: dict[str, Any]) -> None:
        for key in keys:
            self._changes[key] = _clean(key, user_input.get(key))

    def _options_of(self, service: str) -> dict[str, Any]:
        """A followed fuel's options with the changes made here, for either fuel."""
        if service == self._own_service():
            return self._effective()
        entry = self._entry_for(service)
        merged = dict(entry.options) if entry else {}
        for key, value in self._other_changes.get(service, {}).items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        return merged

    # -- the menu --------------------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._service, self._adding = self._own_service(), False
        gas = self._service == SERVICE_GAS
        options = self._effective()
        pages = ["tariff_electricity", "tariff_gas", "meters_gas" if gas else "meters"]
        if not gas:
            pages.append("battery")
        if CONF_MANUAL not in self.config_entry.data:
            pages.append("store")
        if self._dirty():
            pages.append("confirm")
        return self.async_show_menu(
            step_id="init",
            menu_options=pages,
            description_placeholders={
                "unsaved": "You have unsaved changes.\n\n" if self._dirty() else "",
                "electricity_summary": self._tariff_line(SERVICE_ELECTRICITY),
                "gas_summary": self._tariff_line(SERVICE_GAS),
                "meters_summary": meters_line(options, self._service),
                "battery_summary": battery_line(options),
                "windows_summary": windows_line(options),
                "store_summary": self._store_line(),
                "save_note": "Applies every change on the other pages and reloads the entry.",
            },
        )

    def _store_line(self) -> str:
        if self._clear:
            return "the saved files will be deleted and read again when you save"
        if self._refresh:
            return "the store will be read again when you save"
        return "read the store again, or delete the saved files"

    # -- the tariff ------------------------------------------------------------------------------

    async def async_step_tariff_electricity(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._tariff_of(SERVICE_ELECTRICITY)

    async def async_step_tariff_gas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._tariff_of(SERVICE_GAS)

    async def _tariff_of(self, service: str) -> ConfigFlowResult:
        """Choose the plan of one fuel, with the setup pages. A fuel not followed yet is added."""
        self._service = service
        self._reset_pick()
        if self._entry_for(service) is None:
            self._adding = True
            return await self.async_step_country()
        self._adding = False
        return await self.async_step_tariff()

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a different plan, or go back. The sensors keep their names and history."""
        return self.async_show_menu(
            step_id="tariff",
            menu_options=["country", "bills", "windows", "init"],
            description_placeholders={
                "tariff_summary": self._tariff_line(self._service),
                "bills_summary": bills_line(self._options_of(self._service)),
                "windows_summary": windows_line(self._options_of(self._service)),
            },
        )

    async def _plan_ready(
        self, unique: str, title: str, plan: dict[str, Any]
    ) -> ConfigFlowResult:
        """A plan was chosen. Keep it until Save changes, or ask for a new fuel's meters."""
        target = self._entry_for(self._service)
        taken = [
            entry
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.unique_id == unique and (target is None or entry.entry_id != target.entry_id)
        ]
        if taken:
            return self.async_abort(reason="already_configured")
        staged = _StagedPlan(unique, title, plan)
        if target is None:
            self._new_fuel = _NewFuel(self._service, staged, {})
            return await self._new_options_page(None)
        if unique == target.unique_id:
            self._new_plans.pop(self._service, None)
            return await self.async_step_init()
        self._new_plans[self._service] = staged
        return await self.async_step_plan_bills()

    async def async_step_plan_bills(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The page after a plan is chosen: where a bill starts and how long it runs."""
        return await self._bills_page("plan_bills", user_input)

    async def async_step_bills(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The bill dates of the fuel chosen on the tariff page, without changing its plan."""
        return await self._bills_page("bills", user_input)

    async def _bills_page(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        keys = _BILL_KEYS[:3] if self._service == SERVICE_GAS else _BILL_KEYS
        fields = self._bill_fields_for(self._service)
        return await self._fuel_page(step_id, fields, keys, user_input)

    async def _fuel_page(
        self,
        step_id: str,
        fields: dict[Any, Any],
        keys: tuple[str, ...],
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """A page of the fuel chosen on the tariff page. Its answers are kept for that fuel."""
        if user_input is None:
            return self.async_show_form(step_id=step_id, data_schema=_schema(fields))
        changes = {key: _clean(key, user_input.get(key)) for key in keys}
        if self._service == self._own_service():
            self._changes.update(changes)
        else:
            self._other_changes.setdefault(self._service, {}).update(changes)
        return await self.async_step_init()

    def _bill_fields_for(self, service: str) -> dict[Any, Any]:
        options = self._options_of(service)
        fields = _bill_fields(options)
        if service != SERVICE_GAS:
            fields[_suggest(CONF_CONNECTED_LOAD, options)] = _number("kW")
        return fields

    # -- one page for each topic -----------------------------------------------------------------

    async def _page(
        self,
        step_id: str,
        fields: dict[Any, Any],
        keys: tuple[str, ...],
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id=step_id, data_schema=_schema(fields))
        self._stage(keys, user_input)
        return await self.async_step_init()

    async def async_step_meters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        fields = {
            key: value
            for key, value in _meter_fields(self._effective()).items()
            if str(key) in _METER_KEYS
        }
        fields[_suggest(CONF_MAX_METER_KW, self._effective())] = _number("kW")
        return await self._page("meters", fields, (*_METER_KEYS, CONF_MAX_METER_KW), user_input)

    async def async_step_meters_gas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        fields = _gas_meter_fields(self._effective())
        return await self._page("meters_gas", fields, _GAS_METER_KEYS, user_input)

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = self._effective()
        energy = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="energy"))
        charge = EntitySelector(EntitySelectorConfig(domain="sensor", device_class="battery"))
        fields = {
            _suggest(CONF_BATTERY_DISCHARGE_ENERGY, options): energy,
            _suggest(CONF_BATTERY_SOC, options): charge,
            _suggest(CONF_BATTERY_CAPACITY, options): _number("kWh"),
            _suggest(CONF_BATTERY_WEAR, options): _number(),
        }
        return await self._page("battery", fields, _BATTERY_KEYS, user_input)

    async def async_step_windows(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = self._options_of(self._service)
        minutes = NumberSelectorConfig(
            min=MIN_WINDOW_MINUTES,
            max=MAX_WINDOW_MINUTES,
            step=WINDOW_STEP_MINUTES,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="min",
        )
        fields = {
            vol.Required(
                CONF_WINDOW_MINUTES,
                default=options.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES),
            ): NumberSelector(minutes),
            vol.Required(CONF_CHEAP_RULE, default=options.get(CONF_CHEAP_RULE, CHEAP_BAND)): (
                SelectSelector(
                    SelectSelectorConfig(options=list(CHEAP_RULES), translation_key="cheap_rule")
                )
            ),
        }
        return await self._fuel_page("windows", fields, _WINDOW_KEYS, user_input)

    async def async_step_store(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Read the store again, or delete the saved files. Both happen when you save."""
        errors: dict[str, str] = {}
        if user_input is not None:
            clear = bool(user_input.get(CONF_CLEAR_CACHE))
            if clear and self.config_entry.runtime_data.access.offline:
                errors["base"] = "clear_while_offline"  # the files are all there is to run on
            else:
                self._refresh = bool(user_input.get(CONF_REFRESH_NOW))
                self._clear = clear
                return await self.async_step_init()
        fields = {
            vol.Optional(CONF_REFRESH_NOW, default=self._refresh): bool,
            vol.Optional(CONF_CLEAR_CACHE, default=self._clear): bool,
        }
        return self.async_show_form(step_id="store", data_schema=_schema(fields), errors=errors)

    # -- the fuel that is not followed yet -------------------------------------------------------

    async def async_step_new_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._new_options_page(user_input)

    async def async_step_new_options_gas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._new_options_page(user_input)

    async def _new_options_page(self, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        """The new fuel's meters and bill dates, suggested from the Energy dashboard."""
        fuel = self._new_fuel
        assert fuel is not None  # noqa: S101  set by _plan_ready before this page
        gas = fuel.service == SERVICE_GAS
        if user_input is not None:
            fuel.options = _saved_setup(user_input)
            return await self.async_step_init()
        if gas:
            suggested = await gas_dashboard_meter(self.hass)
            fields = {**_gas_meter_fields(suggested), **_bill_fields(suggested)}
        else:
            suggested = await energy_dashboard_meters(self.hass)
            fields = {**_meter_fields(suggested), **_bill_fields(suggested)}
        return self.async_show_form(
            step_id="new_options_gas" if gas else "new_options", data_schema=_schema(fields)
        )

    # -- save ------------------------------------------------------------------------------------

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Write the plans, the options and the new fuel together, and reload each entry once."""
        entry = self.config_entry
        options = self._effective()
        changed = options != dict(entry.options) or self._own_service() in self._new_plans
        for service, plan in self._new_plans.items():
            self._apply_plan(service, plan)
        self._apply_other_options()
        if (self._refresh or self._clear) and self._own_service() not in self._new_plans:
            await entry.runtime_data.async_refresh_store(clear=self._clear)
        if self._new_fuel:
            await self._create_new_fuel(self._new_fuel)
        if changed:
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_create_entry(data=options)

    def _apply_other_options(self) -> None:
        """The bill dates chosen for the other followed fuel are saved on its own entry."""
        for service, changes in self._other_changes.items():
            target = self._entry_for(service)
            if target is None or not changes:
                continue
            options = self._options_of(service)
            self.hass.config_entries.async_update_entry(target, options=options)
            self.hass.config_entries.async_schedule_reload(target.entry_id)

    def _apply_plan(self, service: str, plan: _StagedPlan) -> None:
        """Move a followed fuel to its new plan. Its entity key stays, so its entities do too."""
        target = self._entry_for(service)
        assert target is not None  # noqa: S101  a plan is only staged for a followed fuel
        key = target.data.get("entity_key") or target.unique_id or target.entry_id
        self.hass.config_entries.async_update_entry(
            target,
            unique_id=plan.unique,
            title=plan.title,
            data=entry_data(plan.data, service, plan.title, key),
        )
        if target.entry_id != self.config_entry.entry_id:
            self.hass.config_entries.async_schedule_reload(target.entry_id)

    async def _create_new_fuel(self, fuel: _NewFuel) -> None:
        await self.hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data={
                "service": fuel.service,
                "unique": fuel.plan.unique,
                "title": fuel.plan.title,
                "plan": fuel.plan.data,
                "options": fuel.options,
            },
        )
