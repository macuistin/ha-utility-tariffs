"""Choose a tariff from the open store: country, provider, plan and, where there is one, area."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    CountrySelector,
    CountrySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AREA,
    CONF_COUNTRY,
    CONF_NAME,
    CONF_PROVIDER,
    CONF_TARIFF,
    CONF_WINDOW_MINUTES,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
    MAX_WINDOW_MINUTES,
    MIN_WINDOW_MINUTES,
    WINDOW_STEP_MINUTES,
)
from .lib.tariffstore import StoreError
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


class UtilityTariffsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Four short steps, each limited to what the store holds."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WindowOptionsFlow:
        return WindowOptionsFlow()

    def __init__(self) -> None:
        self._chosen: dict[str, str] = {}
        self._names: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        access = store_access(self.hass)
        try:
            held = [
                code for code, row in (await access.async_countries()).items() if "path" in row
            ]
        except STORE_ERRORS:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            self._chosen[CONF_COUNTRY] = user_input[CONF_COUNTRY]
            return await self.async_step_provider()
        schema = _schema(
            {vol.Required(CONF_COUNTRY): CountrySelector(CountrySelectorConfig(countries=held))}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        access = store_access(self.hass)
        try:
            providers = await access.async_providers(self._chosen[CONF_COUNTRY])
        except STORE_ERRORS:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            self._chosen[CONF_PROVIDER] = user_input[CONF_PROVIDER]
            self._names["provider"] = providers[user_input[CONF_PROVIDER]]
            return await self.async_step_tariff()
        return self.async_show_form(step_id="provider", data_schema=_choice(CONF_PROVIDER, providers))

    async def async_step_tariff(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        access = store_access(self.hass)
        today = dt_util.now().date()
        try:
            tariffs = await access.async_tariffs(
                self._chosen[CONF_COUNTRY], self._chosen[CONF_PROVIDER], today
            )
        except STORE_ERRORS:
            return self.async_abort(reason="cannot_connect")
        if not tariffs:
            return self.async_abort(reason="no_tariffs")
        if user_input is not None:
            self._chosen[CONF_TARIFF] = user_input[CONF_TARIFF]
            self._names["tariff"] = tariffs[user_input[CONF_TARIFF]]
            return await self.async_step_area()
        return self.async_show_form(step_id="tariff", data_schema=_choice(CONF_TARIFF, tariffs))

    async def async_step_area(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
            return self.async_show_form(step_id="area", data_schema=_choice(CONF_AREA, areas))
        self._chosen[CONF_AREA] = user_input[CONF_AREA]
        suffix = "" if len(areas) == 1 else f" ({areas[user_input[CONF_AREA]]})"
        return await self._create(f"{self._names['provider']} {self._names['tariff']}{suffix}")

    async def _create(self, title: str) -> ConfigFlowResult:
        unique = "/".join(
            self._chosen[key] for key in (CONF_COUNTRY, CONF_PROVIDER, CONF_TARIFF, CONF_AREA)
        )
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=title, data={**self._chosen, CONF_NAME: title})


class WindowOptionsFlow(OptionsFlowWithReload):
    """The length of the cheapest and dearest windows. Saving reloads the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={CONF_WINDOW_MINUTES: int(user_input[CONF_WINDOW_MINUTES])})
        current = self.config_entry.options.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES)
        schema = _schema(
            {
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
        )
        return self.async_show_form(step_id="init", data_schema=schema)
