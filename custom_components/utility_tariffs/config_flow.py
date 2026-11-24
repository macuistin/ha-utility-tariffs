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
    SERVICE_ELECTRICITY,
    SERVICE_GAS,
    SERVICES,
)
from .energy_suggest import energy_dashboard_meters, gas_dashboard_meter
from .option_fields import _bill_fields, _gas_meter_fields, _meter_fields, _saved_setup
from .options_flow import TariffOptionsFlow
from .plan_steps import PlanSteps, _schema, entry_data, service_data


class UtilityTariffsConfigFlow(PlanSteps, ConfigFlow, domain=DOMAIN):
    """Country, then supplier and plan together, then an area only where the plan has one."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TariffOptionsFlow:
        return TariffOptionsFlow()

    def __init__(self) -> None:
        super().__init__()
        self._pending: tuple[str, str, dict[str, Any]] = ("", "", {})

    def _current_country(self) -> str | None:
        """On reconfigure the list starts at the followed plan's country."""
        if self.source != SOURCE_RECONFIGURE:
            return None
        country = self._get_reconfigure_entry().data.get(CONF_COUNTRY)
        return country if isinstance(country, str) else None

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


    async def async_step_import(self, data: dict[str, Any]) -> ConfigFlowResult:
        """A plan chosen in Configure, for the fuel that is not followed yet."""
        self._service = data["service"]
        return await self._save(data["unique"], data["title"], data["plan"], data["options"])

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

    async def _plan_ready(
        self, unique: str, title: str, plan: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self._finish(unique, title, plan)

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
        return service_data(self._service)

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
                data=entry_data(plan, self._service, title, key),
            )
        return self.async_create_entry(
            title=title,
            data=entry_data(plan, self._service, title, unique),
            options=options or {},
        )
