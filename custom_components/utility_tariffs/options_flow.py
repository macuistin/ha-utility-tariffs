"""Configure: a menu of pages, each opened, changed and returned from, and saved together.

  init        the menu: Electricity tariff, Gas tariff, the meters of each, Battery, Tariff store,
              each with a line on what is set now, and Save changes once something has changed
  tariff      choose a different plan for a fuel, through the same pages as setup (country, plan,
              area or own rates), or change its bills or windows. A fuel not followed yet is added
  meters, battery, store    one topic each, and gas has its own meters page

One entry holds both fuels, so this one flow changes either. Nothing is written until Save
changes. The pages keep their answers on the flow, and the plans, a new fuel and the settings of
each fuel are applied together in `async_step_confirm`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult, ConfigSubentry, OptionsFlow
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from .backfill import async_fill_history
from .const import (
    CHEAP_BAND,
    CHEAP_RULES,
    CONF_BACKFILL_NOW,
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
    CONF_WINDOW_MINUTES,
    DEFAULT_WINDOW_MINUTES,
    MAX_WINDOW_MINUTES,
    MIN_WINDOW_MINUTES,
    SERVICE_ELECTRICITY,
    SERVICE_GAS,
    WINDOW_STEP_MINUTES,
)
from .energy_suggest import energy_dashboard_meters, gas_dashboard_meter
from .fuel import Fuel
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
from .plan_steps import PLAN_KEYS, PlanSteps, _schema, entry_data

_LOGGER = logging.getLogger(__name__)
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
    """The pages for both fuels. Saving reloads the entry once, whatever was changed."""

    def __init__(self) -> None:
        super().__init__()
        self._changes: dict[str, dict[str, Any]] = {}  # each followed fuel's changed settings
        self._new_plans: dict[str, _StagedPlan] = {}  # a new plan for each fuel already followed
        self._new_fuel: _NewFuel | None = None
        self._refresh = False
        self._clear = False
        self._backfill: set[str] = set()  # fuels whose history is filled when saved

    # -- what each fuel is and what would change -------------------------------------------------

    def _sub(self, service: str) -> ConfigSubentry | None:
        """The subentry that follows this fuel, or None when it is not followed yet."""
        for subentry in self.config_entry.subentries.values():
            if subentry.subentry_type == service:
                return subentry
        return None

    def _options_of(self, service: str) -> dict[str, Any]:
        """A followed fuel's settings with the changes made here."""
        sub = self._sub(service)
        merged = dict(sub.data) if sub else {}
        for key, value in self._changes.get(service, {}).items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        return merged

    def _dirty(self) -> bool:
        return bool(
            self._new_plans
            or any(self._changes.values())
            or self._new_fuel
            or self._refresh
            or self._clear
            or self._backfill
        )

    def _current_country(self) -> str | None:
        sub = self._sub(self._service)
        country = sub.data.get("country") if sub else None
        return country if isinstance(country, str) else None

    def _tariff_line(self, service: str) -> str:
        """What the Electricity tariff and Gas tariff rows say: the plan now, or the one chosen."""
        sub = self._sub(service)
        if sub is None:
            if self._new_fuel and self._new_fuel.service == service:
                return f"{self._new_fuel.plan.title} is added when you save"
            return f"not followed yet, choose a {service} plan"
        staged = self._new_plans.get(service)
        line = tariff_line(sub.title, sub.data, staged.title if staged else None)
        options = self._options_of(service)
        if options.get(CONF_BILL_START_DAY) or options.get(CONF_BILL_MONTHS):
            line += f", {bills_line(options)}"
        return line

    def _meters_line(self, service: str) -> str:
        line = meters_line(self._options_of(service), service)
        return line + (", history is filled when you save" if service in self._backfill else "")

    # -- the menu --------------------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._service = SERVICE_ELECTRICITY
        pages = ["tariff_electricity", "tariff_gas"]
        if self._sub(SERVICE_ELECTRICITY):
            pages += ["meters", "battery"]
        if self._sub(SERVICE_GAS):
            pages.append("meters_gas")
        if self._has_store():
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
                "meters_summary": self._meters_line(SERVICE_ELECTRICITY),
                "meters_gas_summary": self._meters_line(SERVICE_GAS),
                "battery_summary": battery_line(self._options_of(SERVICE_ELECTRICITY)),
                "store_summary": self._store_line(),
                "save_note": "Applies every change on the other pages and reloads the entry.",
            },
        )

    def _has_store(self) -> bool:
        """The store is read for every plan except the household's own rates."""
        return any(CONF_MANUAL not in sub.data for sub in self.config_entry.subentries.values())

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
        if self._sub(service) is None:
            return await self.async_step_country()
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
        target = self._sub(self._service)
        taken = [
            sub
            for sub in self.config_entry.subentries.values()
            if sub.unique_id == unique and (target is None or sub.subentry_id != target.subentry_id)
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
        return await self._page(step_id, fields, keys, user_input)

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
        """A page of the fuel in `_service`. Its answers are kept for that fuel."""
        if user_input is None:
            return self.async_show_form(step_id=step_id, data_schema=_schema(fields))
        changes = self._changes.setdefault(self._service, {})
        changes.update({key: _clean(key, user_input.get(key)) for key in keys})
        return await self.async_step_init()

    async def async_step_meters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._service = SERVICE_ELECTRICITY
        options = self._options_of(SERVICE_ELECTRICITY)
        fields = {
            key: value
            for key, value in _meter_fields(options).items()
            if str(key) in _METER_KEYS
        }
        fields[_suggest(CONF_MAX_METER_KW, options)] = _number("kW")
        keys = (*_METER_KEYS, CONF_MAX_METER_KW)
        return await self._meters_page("meters", fields, keys, user_input)

    async def async_step_meters_gas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._service = SERVICE_GAS
        fields = _gas_meter_fields(self._options_of(SERVICE_GAS))
        return await self._meters_page("meters_gas", fields, _GAS_METER_KEYS, user_input)

    async def _meters_page(
        self,
        step_id: str,
        fields: dict[Any, Any],
        keys: tuple[str, ...],
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """The meters, with a tick to fill the history from their statistics when you save."""
        fields[vol.Optional(CONF_BACKFILL_NOW, default=self._service in self._backfill)] = bool
        if user_input is not None and user_input.get(CONF_BACKFILL_NOW):
            if not user_input.get(CONF_IMPORT_ENERGY):
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=_schema(fields),
                    errors={"base": "backfill_needs_meter"},
                )
        if user_input is not None:
            if user_input.get(CONF_BACKFILL_NOW):
                self._backfill.add(self._service)
            else:
                self._backfill.discard(self._service)
        return await self._page(step_id, fields, keys, user_input)

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._service = SERVICE_ELECTRICITY
        options = self._options_of(SERVICE_ELECTRICITY)
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
        return await self._page("windows", fields, _WINDOW_KEYS, user_input)

    async def async_step_store(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Read the store again, or delete the saved files. Both happen when you save."""
        errors: dict[str, str] = {}
        if user_input is not None:
            clear = bool(user_input.get(CONF_CLEAR_CACHE))
            if clear and any(c.access.offline for c in self.config_entry.runtime_data.values()):
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
        """Write the plans, the settings and the new fuel together, and reload the entry once."""
        entry = self.config_entry
        changed = self._write_fuels()
        if (self._refresh or self._clear) and not changed:
            for coordinator in entry.runtime_data.values():
                await coordinator.async_refresh_store(clear=self._clear)
        for service in self._backfill:
            if service not in changed:
                await self._fill_history(service)  # a reload does it too, so only without one
        if self._new_fuel:
            self._add_fuel(self._new_fuel)  # adding a fuel reloads the entry by itself
        elif changed or self._refresh or self._clear:
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_create_entry(data={})

    def _write_fuels(self) -> set[str]:
        """Save each fuel that has a staged plan or changed settings. Returns the fuels changed."""
        changed: set[str] = set()
        for service in {*self._changes, *self._new_plans}:
            sub = self._sub(service)
            if sub is None or not (self._changes.get(service) or service in self._new_plans):
                continue
            self._write(sub, service)
            changed.add(service)
        return changed

    def _write(self, sub: ConfigSubentry, service: str) -> None:
        """Move a fuel to its staged plan and settings. Its entity key stays, so its entities do."""
        settings = self._options_of(service)
        plan = self._new_plans.get(service)
        title, unique = sub.title, sub.unique_id
        if plan is not None:
            key = Fuel(self.config_entry, sub.subentry_id).key
            kept = {k: v for k, v in settings.items() if k not in PLAN_KEYS}
            settings = {**kept, **entry_data(plan.data, service, plan.title, key)}
            title, unique = plan.title, plan.unique
        self.hass.config_entries.async_update_subentry(
            self.config_entry, sub, data=settings, title=title, unique_id=unique
        )

    async def _fill_history(self, service: str) -> None:
        for coordinator in self.config_entry.runtime_data.values():
            if coordinator.service != service or coordinator.accountant is None:
                continue
            try:
                await async_fill_history(coordinator, coordinator.accountant)
            except (OSError, ValueError, KeyError, TypeError) as err:
                _LOGGER.warning("The meter history could not be filled: %s", err)

    def _add_fuel(self, fuel: _NewFuel) -> None:
        """Follow a fuel that was not followed yet, with its plan, meters and bill dates."""
        data = {**entry_data(fuel.plan.data, fuel.service, fuel.plan.title, fuel.plan.unique)}
        data.update(fuel.options)
        self.hass.config_entries.async_add_subentry(
            self.config_entry,
            ConfigSubentry(
                data=MappingProxyType(data),
                subentry_type=fuel.service,
                title=fuel.plan.title,
                unique_id=fuel.plan.unique,
            ),
        )
