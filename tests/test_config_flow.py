"""Choosing a tariff from the store, against a real flow manager."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.utility_tariffs.const import DOMAIN


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_a_plan_with_areas_is_chosen_in_four_steps(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _start(hass)
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "IE"})
    assert result["step_id"] == "provider"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"provider": "p"})
    assert result["step_id"] == "tariff"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"tariff": "plan"})
    assert result["step_id"] == "area"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"area": "urban"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "P Energy Plan (Urban)"
    assert result["data"] == {
        "country": "IE",
        "provider": "p",
        "tariff": "plan",
        "area": "urban",
        "name": "P Energy Plan (Urban)",
    }
    assert result["result"].unique_id == "IE/p/plan/urban"


async def test_a_plan_with_one_price_skips_the_area_step(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "IE"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"provider": "p"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"tariff": "flat"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "P Energy Flat"
    assert result["data"]["area"] == "all"


async def test_the_same_plan_cannot_be_added_twice(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="IE/p/flat/all", data={}).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "IE"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"provider": "p"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"tariff": "flat"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_only_countries_the_store_holds_are_offered(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    result = await _start(hass)
    selector = result["data_schema"].schema["country"]
    assert selector.config["countries"] == ["IE"]  # the store also lists one it has no tariffs for


async def test_an_unreachable_store_with_nothing_cached_aborts(
    hass: HomeAssistant, use_store: Callable[..., Path]
) -> None:
    def unreachable(path: str) -> bytes:
        raise OSError("no network")

    use_store(unreachable)
    result = await _start(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
