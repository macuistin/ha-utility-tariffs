"""One followed tariff: a subentry of the integration's single config entry.

The entry holds the hub, and each fuel (electricity, gas) is a subentry with its own plan, meters
and bill dates. `Fuel` reads the subentry fresh each time, so a change saved in Configure is seen
at once, and it offers what the code used to ask of a config entry of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .const import CONF_ENTITY_KEY, CONF_SERVICE, SERVICE_ELECTRICITY

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.core import HomeAssistant

CONF_STORE_KEY = "store_key"  # where a moved entry's saved energy history already lives


class Fuel:
    """A view of one subentry: its settings, its title and its stable keys."""

    def __init__(self, entry: ConfigEntry[Any], subentry_id: str) -> None:
        self.entry = entry
        self.subentry_id = subentry_id
        # Read once: it is still needed after the subentry is removed, to delete its history.
        self.store_key = str(self.data.get(CONF_STORE_KEY) or subentry_id)

    @property
    def subentry(self) -> ConfigSubentry:
        return self.entry.subentries[self.subentry_id]

    @property
    def data(self) -> Mapping[str, Any]:
        return self.subentry.data

    @property
    def options(self) -> Mapping[str, Any]:
        """The same settings as `data`: a subentry has one store for the plan and the options."""
        return self.subentry.data

    @property
    def title(self) -> str:
        return self.subentry.title

    @property
    def unique_id(self) -> str | None:
        return self.subentry.unique_id

    @property
    def service(self) -> str:
        return str(self.data.get(CONF_SERVICE, SERVICE_ELECTRICITY))

    @property
    def key(self) -> str:
        """Fixed when the fuel is first followed, so a new plan keeps its entities and ids."""
        return str(self.data.get(CONF_ENTITY_KEY) or self.unique_id or self.subentry_id)

    def async_create_background_task(
        self, hass: HomeAssistant, target: Coroutine[Any, Any, Any], name: str
    ) -> Any:
        return self.entry.async_create_background_task(hass, target, name)

    def async_on_unload(self, func: Callable[[], Any]) -> None:
        self.entry.async_on_unload(func)

    def async_update(self, hass: HomeAssistant, data: Mapping[str, Any]) -> None:
        """Replace the settings. Nothing reloads: the sensors read them each time."""
        hass.config_entries.async_update_subentry(self.entry, self.subentry, data=dict(data))
