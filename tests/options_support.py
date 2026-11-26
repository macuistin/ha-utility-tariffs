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


async def fill_bills(
    hass: HomeAssistant, flow_id: str, service: str, user_input: dict[str, Any]
) -> dict[str, Any]:
    """The bill dates are on the fuel's tariff page: open the tariff, then Bills."""
    flow = hass.config_entries.options
    await flow.async_configure(flow_id, {"next_step_id": f"tariff_{service}"})
    result = await flow.async_configure(flow_id, {"next_step_id": "bills"})
    assert result["step_id"] == "bills"
    result = await flow.async_configure(flow_id, user_input)
    assert result["step_id"] == "init"
    return result


async def fill_windows(
    hass: HomeAssistant, flow_id: str, service: str, user_input: dict[str, Any]
) -> dict[str, Any]:
    """The windows are on the fuel's tariff page too: open the tariff, then Cheap and dear windows."""
    flow = hass.config_entries.options
    await flow.async_configure(flow_id, {"next_step_id": f"tariff_{service}"})
    result = await flow.async_configure(flow_id, {"next_step_id": "windows"})
    assert result["step_id"] == "windows"
    result = await flow.async_configure(flow_id, user_input)
    assert result["step_id"] == "init"
    return result


async def configure(
    hass: HomeAssistant, entry_id: str, service: str = "electricity", **pages: dict[str, Any]
) -> dict[str, Any]:
    """Fill each named page, then choose Done. Returns the result of closing."""
    flow = await open_menu(hass, entry_id)
    for page, user_input in pages.items():
        if page == "bills":
            flow = await fill_bills(hass, flow["flow_id"], service, user_input)
        elif page == "windows":
            flow = await fill_windows(hass, flow["flow_id"], service, user_input)
        else:
            flow = await fill_page(hass, flow["flow_id"], page, user_input)
    return await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "done"}
    )
