"""Drive Configure the way a person does: open a page from the menu, fill it, then save."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant


async def open_menu(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    result = await hass.config_entries.options.async_init(entry_id)
    assert result["step_id"] == "init"
    return result


async def fill_page(
    hass: HomeAssistant, flow_id: str, page: str, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Open one page from the menu and submit it. Returns the menu again."""
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": page})
    assert result["step_id"] == page
    result = await hass.config_entries.options.async_configure(flow_id, user_input)
    assert result["step_id"] == "init"
    return result


async def configure(
    hass: HomeAssistant, entry_id: str, **pages: dict[str, Any]
) -> dict[str, Any]:
    """Fill each named page, then choose Save changes. Returns the result of the save."""
    flow = await open_menu(hass, entry_id)
    for page, user_input in pages.items():
        flow = await fill_page(hass, flow["flow_id"], page, user_input)
    return await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "confirm"}
    )
