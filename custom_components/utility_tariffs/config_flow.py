"""Set up a tariff from the open store: service, country, provider, plan and, where there is one, area.

The plan pages are in `plan_steps.py` and the Configure pages in `options_flow.py`.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryData,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_COUNTRY,
    CONF_ENTITY_KEY,
    CONF_SERVICE,
    DOMAIN,
    FUEL_TITLES,
    HUB_NAME,
    SERVICE_ELECTRICITY,
    SERVICE_GAS,
    SERVICES,
)
from .energy_suggest import energy_dashboard_meters, gas_dashboard_meter
from .migrate import ENTRY_VERSION
from .option_fields import _bill_fields, _gas_meter_fields, _meter_fields, _saved_setup
from .options_flow import TariffOptionsFlow
from .plan_steps import PLAN_KEYS, PlanSteps, _schema, entry_data, service_data


class UtilityTariffsConfigFlow(PlanSteps, ConfigFlow, domain=DOMAIN):
    """Country, then supplier and plan together, then an area only where the plan has one."""

    VERSION = ENTRY_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TariffOptionsFlow:
        return TariffOptionsFlow()

    def __init__(self) -> None:
        super().__init__()
        self._pending: tuple[str, str, dict[str, Any]] = ("", "", {})
        self._reconfigured: ConfigSubentry | None = None

    def _current_country(self) -> str | None:
        """On reconfigure the list starts at the followed plan's country."""
        subentry = self._reconfigured
        country = subentry.data.get(CONF_COUNTRY) if subentry else None
        return country if isinstance(country, str) else None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: the first fuel to follow. The other is added later, in Configure."""
        await self.async_set_unique_id(DOMAIN, raise_on_progress=False)
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            self._service = user_input[CONF_SERVICE]
            return await self.async_step_country()
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(
                {
                    vol.Required(CONF_SERVICE, default=SERVICE_ELECTRICITY): SelectSelector(
                        SelectSelectorConfig(
                            options=list(SERVICES),
                            translation_key="service",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            last_step=False,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Follow a different plan for a fuel. The entities keep their ids and history."""
        entry = self._get_reconfigure_entry()
        fuels = {sub.subentry_type: sub for sub in entry.subentries.values()}
        if user_input is None and len(fuels) > 1:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=_schema(
                    {
                        vol.Required(CONF_SERVICE, default=SERVICE_ELECTRICITY): SelectSelector(
                            SelectSelectorConfig(
                                options=list(fuels),
                                translation_key="service",
                                mode=SelectSelectorMode.LIST,
                            )
                        )
                    }
                ),
            )
        chosen = user_input[CONF_SERVICE] if user_input else next(iter(fuels), None)
        if chosen is None:
            return self.async_abort(reason="no_tariff")
        self._reconfigured = fuels[chosen]
        self._service = chosen
        return await self.async_step_country()

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
            return self._save(*self._pending, options=_saved_setup(user_input))
        if self._service == SERVICE_GAS:
            suggested = await gas_dashboard_meter(self.hass)
            fields = {**_gas_meter_fields(suggested), **_bill_fields(suggested)}
        else:
            suggested = await energy_dashboard_meters(self.hass)
            fields = {**_meter_fields(suggested), **_bill_fields(suggested)}
        return self.async_show_form(step_id=step_id, data_schema=_schema(fields))

    async def _plan_ready(
        self, unique: str, title: str, plan: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self._finish(unique, title, plan)

    async def _finish(self, unique: str, title: str, plan: dict[str, Any]) -> ConfigFlowResult:
        """Ask for the options when making a new entry. A plan change keeps what is set."""
        if self.source == SOURCE_RECONFIGURE:
            others = self._get_reconfigure_entry().subentries.values()
            followed = {sub.unique_id for sub in others if sub is not self._reconfigured}
            if unique in followed:
                return self.async_abort(reason="already_configured")
            return self._save(unique, title, plan)
        self._pending = (unique, title, plan)
        if self._service == SERVICE_GAS:
            return await self.async_step_options_gas()
        return await self.async_step_options()

    def _service_data(self) -> dict[str, str]:
        """The service, written only when it is not the default so older entries read the same."""
        return service_data(self._service)

    def _save(
        self, unique: str, title: str, plan: dict[str, Any], options: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Make the entry with its first fuel, or on reconfigure move a fuel to this plan."""
        if self._reconfigured is not None:
            return self._save_reconfigured(self._reconfigured, unique, title, plan)
        data = {**entry_data(plan, self._service, title, unique), **(options or {})}
        return self.async_create_entry(
            title=HUB_NAME,
            data={},
            subentries=[
                ConfigSubentryData(
                    data=data,
                    subentry_type=self._service,
                    title=FUEL_TITLES[self._service],
                    unique_id=unique,
                )
            ],
        )

    def _save_reconfigured(
        self, subentry: ConfigSubentry, unique: str, title: str, plan: dict[str, Any]
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        key = subentry.data.get(CONF_ENTITY_KEY) or subentry.unique_id or subentry.subentry_id
        kept = {k: v for k, v in subentry.data.items() if k not in PLAN_KEYS}
        self.hass.config_entries.async_update_subentry(
            entry,
            subentry,
            data={**kept, **entry_data(plan, self._service, title, str(key))},
            title=FUEL_TITLES[self._service],
            unique_id=unique,
        )
        self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_abort(reason="reconfigure_successful")
